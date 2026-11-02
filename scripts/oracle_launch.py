"""Keep trying to create the FinAdvisor Always Free Arm VM until Oracle has capacity.

    python scripts/oracle_launch.py            # uses ~/.oci/config and ~/.ssh/finadvisor_oracle.pub

- Sets up (once) a VCN "finadvisor-vcn" with an internet gateway, a default route, ingress for ports 22/80/443 and a
  public subnet. Existing networks are left untouched.
- Tries VM.Standard.A1.Flex, alternating 2 OCPU / 12 GB and 1 OCPU / 6 GB, one request every ~75 s (backoff on rate limits), in
  every availability domain. A smaller VM can be resized later from the console.
- Stops as soon as an instance named "finadvisor" exists, and writes its public IP to ~/.oci/finadvisor_instance.txt.
Only Always Free resources are requested; nothing here upgrades the account.
"""

from __future__ import annotations

import random
import sys
import time
from datetime import datetime
from pathlib import Path

import oci

NAME = "finadvisor"
SHAPES = [(2, 12), (1, 6)]
BASE_DELAY = 75          # seconds between launch requests
HOME = Path.home()
LOG = HOME / ".oci" / "finadvisor_launch.log"
OUT = HOME / ".oci" / "finadvisor_instance.txt"


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def network(cfg, comp: str) -> str:
    vn = oci.core.VirtualNetworkClient(cfg)
    vcn = next((v for v in vn.list_vcns(comp).data if v.display_name == f"{NAME}-vcn" and v.lifecycle_state == "AVAILABLE"), None)
    if vcn is None:
        log("creating network finadvisor-vcn")
        vcn = vn.create_vcn(oci.core.models.CreateVcnDetails(compartment_id=comp, cidr_blocks=["10.0.0.0/16"],
                                                             display_name=f"{NAME}-vcn", dns_label="finadvisor")).data
        oci.wait_until(vn, vn.get_vcn(vcn.id), "lifecycle_state", "AVAILABLE")
    igws = [g for g in vn.list_internet_gateways(comp, vcn_id=vcn.id).data if g.lifecycle_state == "AVAILABLE"]
    igw = igws[0] if igws else vn.create_internet_gateway(oci.core.models.CreateInternetGatewayDetails(
        compartment_id=comp, vcn_id=vcn.id, is_enabled=True, display_name=f"{NAME}-igw")).data
    rt = vn.get_route_table(vcn.default_route_table_id).data
    if not any(r.destination == "0.0.0.0/0" for r in rt.route_rules):
        vn.update_route_table(rt.id, oci.core.models.UpdateRouteTableDetails(route_rules=rt.route_rules + [
            oci.core.models.RouteRule(destination="0.0.0.0/0", destination_type="CIDR_BLOCK", network_entity_id=igw.id)]))
    sl = vn.get_security_list(vcn.default_security_list_id).data
    have = {(r.tcp_options.destination_port_range.min if r.tcp_options and r.tcp_options.destination_port_range else None)
            for r in sl.ingress_security_rules}
    new = [oci.core.models.IngressSecurityRule(protocol="6", source="0.0.0.0/0", tcp_options=oci.core.models.TcpOptions(
        destination_port_range=oci.core.models.PortRange(min=p, max=p))) for p in (22, 80, 443) if p not in have]
    if new:
        vn.update_security_list(sl.id, oci.core.models.UpdateSecurityListDetails(
            ingress_security_rules=sl.ingress_security_rules + new, egress_security_rules=sl.egress_security_rules))
    subnet = next((s for s in vn.list_subnets(comp, vcn_id=vcn.id).data if s.lifecycle_state == "AVAILABLE"), None)
    if subnet is None:
        subnet = vn.create_subnet(oci.core.models.CreateSubnetDetails(
            compartment_id=comp, vcn_id=vcn.id, cidr_block="10.0.0.0/24", display_name=f"{NAME}-subnet",
            dns_label="public", prohibit_public_ip_on_vnic=False)).data
        oci.wait_until(vn, vn.get_subnet(subnet.id), "lifecycle_state", "AVAILABLE")
    return subnet.id


def ubuntu_image(compute, comp: str) -> str:
    imgs = compute.list_images(comp, operating_system="Canonical Ubuntu", operating_system_version="24.04",
                               shape="VM.Standard.A1.Flex", sort_by="TIMECREATED", sort_order="DESC").data
    if not imgs:
        raise SystemExit("No Ubuntu 24.04 Arm image found in this region")
    return imgs[0].id


def existing(compute, comp: str):
    return next((i for i in compute.list_instances(comp, display_name=NAME).data
                 if i.lifecycle_state in ("PROVISIONING", "STARTING", "RUNNING")), None)


def public_ip(cfg, comp: str, inst) -> str | None:
    compute, vn = oci.core.ComputeClient(cfg), oci.core.VirtualNetworkClient(cfg)
    for att in compute.list_vnic_attachments(comp, instance_id=inst.id).data:
        ip = vn.get_vnic(att.vnic_id).data.public_ip
        if ip:
            return ip
    return None


def main() -> None:
    cfg = oci.config.from_file()
    oci.config.validate_config(cfg)
    comp = cfg["tenancy"]
    compute = oci.core.ComputeClient(cfg)
    ads = [a.name for a in oci.identity.IdentityClient(cfg).list_availability_domains(comp).data]
    ssh_pub = (HOME / ".ssh" / "finadvisor_oracle.pub").read_text().strip()
    inst = existing(compute, comp)
    if inst is None:
        subnet = network(cfg, comp)
        image = ubuntu_image(compute, comp)
        log(f"trying {SHAPES} in {ads}; image {image[-12:]}")
        # One launch request per cycle, rotating through shape x AD. Back-to-back requests were rate-limited (429),
        # so the smaller shape was never actually tried; a single request every ~75 s stays under the limit.
        combos = [(ocpu, mem, ad) for ocpu, mem in SHAPES for ad in ads]
        attempt, delay = 0, BASE_DELAY
        while inst is None:
            ocpu, mem, ad = combos[attempt % len(combos)]
            attempt += 1
            try:
                inst = compute.launch_instance(oci.core.models.LaunchInstanceDetails(
                    compartment_id=comp, availability_domain=ad, display_name=NAME, shape="VM.Standard.A1.Flex",
                    shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(ocpus=ocpu, memory_in_gbs=mem),
                    source_details=oci.core.models.InstanceSourceViaImageDetails(image_id=image, boot_volume_size_in_gbs=50),
                    create_vnic_details=oci.core.models.CreateVnicDetails(subnet_id=subnet, assign_public_ip=True),
                    metadata={"ssh_authorized_keys": ssh_pub})).data
                log(f"created: {ocpu} OCPU / {mem} GB in {ad}")
                break
            except oci.exceptions.ServiceError as e:
                if e.status == 429:
                    attempt -= 1                      # retry the same shape after backing off
                    delay = min(delay * 2, 600)
                    log(f"rate limited; waiting {delay}s")
                elif "capacity" in (e.message or "").lower():
                    delay = max(BASE_DELAY, int(delay * 0.7))
                    if attempt % 10 == 0 or attempt <= 2:
                        log(f"attempt {attempt}: no capacity for {ocpu} OCPU / {mem} GB in {ad}")
                else:
                    log(f"stopping on unexpected error {e.status} {e.code}: {e.message}")
                    raise
            time.sleep(delay + random.uniform(0, 15))
    log("waiting for the VM to start")
    inst = oci.wait_until(compute, compute.get_instance(inst.id), "lifecycle_state", "RUNNING", max_wait_seconds=900).data
    ip = None
    for _ in range(30):
        ip = public_ip(cfg, comp, inst)
        if ip:
            break
        time.sleep(10)
    OUT.write_text(f"{ip}\n", encoding="utf-8")
    log(f"RUNNING. Public IP {ip}. SSH: ssh -i ~/.ssh/finadvisor_oracle ubuntu@{ip}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
