/**
 * Demo Settings Component (Research Ablation Toggles)
 * ====================================================
 * In academic AI research and final year capstone presentations, an "ablation study"
 * tests how well a system performs when specific advanced modules are turned OFF vs ON.
 * 
 * This component provides a popover menu allowing the presenter to toggle:
 *   1. Preference Confirmation: Tests whether confirming user preferences prevents misaligned advice.
 *   2. Audit-Constrained Generation: Tests recommendations with vs without strict RAG evidence constraints.
 * 
 * Any toggle change is immediately persisted to the backend API (`/api/ablation`).
 */

import { useEffect, useState } from "react";
import { FlaskConical } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Switch } from "@/components/ui/switch";
import { advisorApi } from "@/lib/advisor/api";
import type { AblationConfig } from "@/lib/advisor/types";

export function DemoSettings({
  onChange,
}: {
  onChange?: (config: AblationConfig) => void;
}) {
  // Current ablation flags state
  const [config, setConfig] = useState<AblationConfig>({
    enable_preference_confirmation: true,
    enable_audit_evidence: true,
  });

  // Fetch the current ablation toggles from the backend on load
  useEffect(() => {
    void advisorApi.getAblation().then(setConfig);
  }, []);

  // Update a flag locally and sync the updated settings to the backend
  const update = async (patch: Partial<AblationConfig>) => {
    const next = { ...config, ...patch };
    setConfig(next);
    const saved = await advisorApi.setAblation(next);
    setConfig(saved);
    onChange?.(saved);
  };

  return (
    <Popover>
      {/* Trigger Button: Shows a flask icon labeled "Demo settings" */}
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="gap-2 border-dashed border-accent/50 text-accent hover:text-accent"
        >
          <FlaskConical className="size-4" />
          Demo settings
        </Button>
      </PopoverTrigger>

      {/* Popover Content Card */}
      <PopoverContent align="end" className="w-80 border-dashed border-accent/50">
        <p className="text-sm font-semibold">Ablation toggles</p>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          Research demo only. Run the same query with a flag on and off to show the ablation
          comparison.
        </p>

        {/* Toggle Switches */}
        <div className="mt-4 space-y-4">
          <Row
            id="pref"
            label="Preference confirmation"
            hint="ENABLE_PREFERENCE_CONFIRMATION"
            checked={config.enable_preference_confirmation}
            onCheckedChange={(v) => void update({ enable_preference_confirmation: v })}
          />
          <Row
            id="audit"
            label="Audit-constrained generation"
            hint="ENABLE_AUDIT_EVIDENCE"
            checked={config.enable_audit_evidence}
            onCheckedChange={(v) => void update({ enable_audit_evidence: v })}
          />
        </div>
      </PopoverContent>
    </Popover>
  );
}

/**
 * Helper row component rendering a label, hint description, and interactive switch
 */
function Row({
  id,
  label,
  hint,
  checked,
  onCheckedChange,
}: {
  id: string;
  label: string;
  hint: string;
  checked: boolean;
  onCheckedChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <Label htmlFor={id} className="text-sm">
          {label}
        </Label>
        <p className="mt-0.5 font-mono text-[0.65rem] text-muted-foreground">{hint}</p>
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  );
}
