# Deploying FinAdvisor (all free tiers)

```
Cloudflare Pages (web/)  ──HTTPS──▶  Oracle Always Free Arm VM: FastAPI + Ollama + cron  ──▶  Supabase Postgres + Auth
```

## 1. Supabase (database and sign-in) — done for project `ciryesycfcxhzdblsyhs`
1. Free projects pause after 7 idle days; the daily data job keeps it active once deployed.
2. `supabase/schema.sql` is applied (RLS on, no policies, so the public Data API exposes nothing).
3. Authentication → URL Configuration: set **Site URL** to the Pages URL once it exists, and add it (plus
   `http://localhost:5173/**`) under **Redirect URLs**.
4. The API connects through the **session pooler** `aws-1-eu-west-3.pooler.supabase.com:5432` (the direct
   `db.*` host is IPv6-only). No service-role key is needed: account deletion removes the sign-in via SQL.

### Google sign-in (optional)
1. <https://console.cloud.google.com> → create a project "FinAdvisor".
2. **Google Auth Platform → Branding**: app name FinAdvisor, your support email. **Audience**: External. While the
   app is in *Testing*, add your team's Gmail addresses under **Test users** (only they can sign in).
3. **Clients → Create client → Web application**:
   - Authorised JavaScript origins: `http://localhost:5173` and later `https://<project>.pages.dev`
   - Authorised redirect URI: `https://ciryesycfcxhzdblsyhs.supabase.co/auth/v1/callback`
4. Copy the **Client ID** and **Client secret** → Supabase → Authentication → **Sign In / Providers → Google** →
   enable, paste both, save.
5. Set `VITE_GOOGLE_AUTH=true` in `web/.env.local` (and in Cloudflare Pages) to show the Google button.

## 2. Oracle Always Free VM (API, model, daily jobs)

### 2.1 Account
1. <https://signup.oracle.com> → Free Tier. Card verification is required; nothing is charged while you stay on
   **Always Free** (do not click "Upgrade to Pay As You Go").
2. **Home region: France Central (Paris)** — it cannot be changed later. Supabase is in Paris (eu-west-3), and the
   API makes many small database round trips; a far region made the first price backfill ~20 min from India.

### 2.2 Create the VM
Console → **Compute → Instances → Create instance**
- Name `finadvisor`. **Image**: Canonical Ubuntu 24.04. **Shape** → Change shape → Ampere →
  **VM.Standard.A1.Flex, 2 OCPU, 12 GB** (the Always Free allowance).
- **Networking**: create a new VCN and public subnet; **Assign a public IPv4 address**: yes.
- **SSH keys**: "Generate a key pair for me" → **download the private key** (you cannot get it again).
- Boot volume: default 50 GB is plenty (Always Free allows up to 200 GB total).
- Create. If you see *Out of host capacity*, try another Availability Domain in the same form, or retry later.

Note the **public IP**, e.g. `141.145.12.34`. Your API address will be `https://141-145-12-34.sslip.io`
(sslip.io maps that name to the IP for free, so HTTPS works without buying a domain).

### 2.3 Open ports 80 and 443
1. Instance page → subnet link → **Security Lists → Default Security List → Add Ingress Rules**: source
   `0.0.0.0/0`, TCP, destination port **80**; repeat for **443**.
2. Oracle's Ubuntu image also blocks ports in iptables; on the VM (next step) run:
   ```bash
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
   sudo netfilter-persistent save
   ```

### 2.4 Install
From your laptop (PowerShell): `ssh -i C:\path\to\ssh-key.key ubuntu@141.145.12.34`
```bash
sudo apt update && sudo apt -y upgrade
sudo apt install -y python3-venv python3-dev git caddy build-essential
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl edit ollama            # add these two lines, then save:
#   [Service]
#   Environment="OLLAMA_KEEP_ALIVE=24h"
sudo systemctl restart ollama
ollama pull qwen2.5:3b
git clone https://github.com/b-rahul07/FinAdv.git && cd FinAdv
python3 -m venv .venv && . .venv/bin/activate
pip install -U pip && pip install -e ".[postgres,cas]"
```
Copy your `.env` from the laptop (it holds the database password; never commit it):
`scp -i C:\path\to\ssh-key.key C:\Users\rahul\OneDrive\Desktop\FinAdvisor\.env ubuntu@141.145.12.34:~/FinAdv/.env`
then edit it on the VM (`nano .env`) so these lines read:
```
APP_ENV=prod
AUTH_MODE=supabase
RETRIEVAL=keyword            # light document search; "chroma" needs torch (~2 GB) — optional later
CORS_ORIGINS=https://<project>.pages.dev
```
Load the stock and fund lists once: `python -m finadvisor.market.jobs masters`

### 2.5 Run the API as a service
`sudo nano /etc/systemd/system/finadvisor.service`:
```ini
[Unit]
Description=FinAdvisor API
After=network-online.target ollama.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/FinAdv
ExecStart=/home/ubuntu/FinAdv/.venv/bin/uvicorn finadvisor.api.app:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload && sudo systemctl enable --now finadvisor
```
One worker is deliberate: the model is the bottleneck, and live-generation state is per process.

`sudo nano /etc/caddy/Caddyfile` (replace the IP):
```
141-145-12-34.sslip.io {
    reverse_proxy 127.0.0.1:8000
}
```
`sudo systemctl reload caddy` — Caddy fetches a Let's Encrypt certificate automatically.
Check: open `https://141-145-12-34.sslip.io/api/status` → `"auth_mode":"supabase"`.

### 2.6 Daily data jobs
`crontab -e` and add (times in UTC = 7:30 pm and 11:45 pm IST, and Monday 6 am IST):
```
0 14 * * *   cd /home/ubuntu/FinAdv && .venv/bin/python -m finadvisor.market.jobs daily   >> jobs.log 2>&1
15 18 * * *  cd /home/ubuntu/FinAdv && .venv/bin/python -m finadvisor.market.jobs daily   >> jobs.log 2>&1
30 0 * * 1   cd /home/ubuntu/FinAdv && .venv/bin/python -m finadvisor.market.jobs masters >> jobs.log 2>&1
```

### 2.7 Updating later
```bash
cd ~/FinAdv && git pull && . .venv/bin/activate && pip install -e ".[postgres,cas]" && sudo systemctl restart finadvisor
```

### Risk to know about
Oracle may reclaim Always Free VMs that stay almost idle for 7 days (very low CPU, network and memory use). Real
users, the twice-daily jobs and the 12 GB model in memory should keep it above the threshold, but check the
instance after the first week. Upgrading to Pay As You Go removes this, but it is a billing account: ask first.

## 3. Cloudflare Pages (web)
dash.cloudflare.com → Workers & Pages → Create → Pages → connect the GitHub repo.
Build command `cd web && npm ci && npm run build`, output directory `web/dist`. Environment variables:
`VITE_API_URL=https://141-145-12-34.sslip.io`, `VITE_SUPABASE_URL=https://ciryesycfcxhzdblsyhs.supabase.co`,
`VITE_SUPABASE_ANON_KEY=<anon key>`, and `VITE_GOOGLE_AUTH=true` if Google is enabled.
`web/public/_redirects` already handles client-side routes. Then put the `*.pages.dev` URL into the VM's
`CORS_ORIGINS` and Supabase's Site URL / Redirect URLs.

## 4. Experiments (Colab / Kaggle)
```bash
pip install -e .          # same finadvisor package as the website
python -m experiments.run experiments/configs/smoke.yaml
```
Results append to `results/<run>/*.jsonl` and resume after a disconnect.

## Limits to remember
- Supabase free: 500 MB DB — prices are stored only for instruments someone holds or watches.
- CPU model: one audited plan ≈ 45–70 s on a laptop CPU; the auditor's 240 s time budget falls back to the safe plan.
- NSE/BSE archives need a browser user agent; requests are spaced ≥ 1 s and each file is fetched once.
