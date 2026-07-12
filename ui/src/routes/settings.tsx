import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { User, Palette, Bot, Key, Bell, Shield, CreditCard, Puzzle, Save } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/settings")({
  head: () => ({ meta: [{ title: "Settings — Atlas Workspace" }, { name: "description", content: "Manage your profile, agents, and workspace." }] }),
  component: SettingsPage,
});

const sections = [
  { id: "profile", label: "Profile", icon: User },
  { id: "appearance", label: "Appearance", icon: Palette },
  { id: "agents", label: "Agents & models", icon: Bot },
  { id: "api", label: "API keys", icon: Key },
  { id: "notifications", label: "Notifications", icon: Bell },
  { id: "security", label: "Security", icon: Shield },
  { id: "billing", label: "Billing", icon: CreditCard },
  { id: "integrations", label: "Integrations", icon: Puzzle },
];

function SettingsPage() {
  const [section, setSection] = useState("profile");
  return (
    <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
      <PageHeader title="Settings" subtitle="Manage your workspace, agents, and account." actions={
        <Button size="sm" className="bg-primary text-primary-foreground hover:bg-primary/90"><Save className="h-4 w-4 mr-1.5" /> Save changes</Button>
      } />
      <div className="flex-1 overflow-hidden grid grid-cols-[240px_minmax(0,1fr)]">
        <nav className="border-r border-border p-3 space-y-0.5 overflow-y-auto">
          {sections.map((s) => (
            <button key={s.id} onClick={() => setSection(s.id)}
              className={cn("w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-sm transition-colors",
                section === s.id ? "bg-surface-2 text-foreground" : "text-muted-foreground hover:bg-surface-2/60 hover:text-foreground")}>
              <s.icon className={cn("h-4 w-4", section === s.id && "text-primary")} /> {s.label}
            </button>
          ))}
        </nav>

        <div className="overflow-y-auto p-6 sm:p-8">
          <div className="max-w-2xl space-y-8">
            {section === "profile" && <ProfileSection />}
            {section === "appearance" && <AppearanceSection />}
            {section === "agents" && <AgentsSection />}
            {section === "api" && <ApiSection />}
            {section === "notifications" && <NotificationsSection />}
            {section === "security" && <SecuritySection />}
            {section === "billing" && <BillingSection />}
            {section === "integrations" && <IntegrationsSection />}
          </div>
        </div>
      </div>
    </div>
  );
}

function Panel({ title, desc, children }: { title: string; desc?: string; children: React.ReactNode }) {
  return (
    <section className="surface-panel p-6">
      <h2 className="text-base font-medium">{title}</h2>
      {desc && <p className="text-sm text-muted-foreground mt-0.5">{desc}</p>}
      <Separator className="my-5" />
      {children}
    </section>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 py-3 first:pt-0">
      <div className="min-w-0">
        <Label className="text-sm">{label}</Label>
        {hint && <p className="text-xs text-muted-foreground mt-0.5">{hint}</p>}
      </div>
      <div>{children}</div>
    </div>
  );
}

function ProfileSection() {
  return (
    <>
      <Panel title="Profile" desc="How you appear across the workspace.">
        <div className="flex items-center gap-4">
          <Avatar className="h-16 w-16">
            <AvatarFallback className="bg-gradient-to-br from-primary to-orange-500 text-primary-foreground text-lg font-semibold">MR</AvatarFallback>
          </Avatar>
          <div className="space-x-2">
            <Button variant="secondary" size="sm">Upload photo</Button>
            <Button variant="ghost" size="sm" className="text-muted-foreground">Remove</Button>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4 mt-6">
          <div className="space-y-1.5"><Label>Full name</Label><Input defaultValue="Maya Rowe" /></div>
          <div className="space-y-1.5"><Label>Display handle</Label><Input defaultValue="@maya" /></div>
          <div className="space-y-1.5 col-span-2"><Label>Email</Label><Input type="email" defaultValue="maya@northwind.co" /></div>
          <div className="space-y-1.5 col-span-2"><Label>Bio</Label><Textarea rows={3} defaultValue="Head of product at Northwind. Building the boring parts of AI infra." /></div>
        </div>
      </Panel>
      <Panel title="Workspace" desc="Shared with your team.">
        <Row label="Workspace name"><Input defaultValue="Northwind Labs" className="w-64" /></Row>
        <Row label="URL slug" hint="atlas.app/w/northwind"><Input defaultValue="northwind" className="w-64 text-mono" /></Row>
        <Row label="Default agent"><Input defaultValue="Atlas · Strategist" className="w-64" /></Row>
      </Panel>
    </>
  );
}

function AppearanceSection() {
  return (
    <Panel title="Appearance" desc="Customize the look and feel of your workspace.">
      <Row label="Theme" hint="Match the OS or lock a mode">
        <div className="flex rounded-md border border-border p-0.5">
          {["System", "Light", "Dark"].map((t, i) => (
            <button key={t} className={cn("px-3 py-1 text-xs rounded", i === 2 ? "bg-surface-3" : "text-muted-foreground")}>{t}</button>
          ))}
        </div>
      </Row>
      <Row label="Accent color">
        <div className="flex gap-1.5">
          {["oklch(0.78 0.14 65)","oklch(0.72 0.15 155)","oklch(0.72 0.12 230)","oklch(0.68 0.18 300)","oklch(0.75 0.18 20)"].map((c,i) => (
            <button key={i} className={cn("h-6 w-6 rounded-full border-2", i === 0 ? "border-foreground" : "border-transparent")} style={{ background: c }} />
          ))}
        </div>
      </Row>
      <Row label="Message density"><div className="flex rounded-md border border-border p-0.5">{["Compact","Comfortable","Spacious"].map((t,i)=><button key={t} className={cn("px-3 py-1 text-xs rounded", i===1?"bg-surface-3":"text-muted-foreground")}>{t}</button>)}</div></Row>
      <Row label="Reduce motion" hint="Disable non-essential animations"><Switch /></Row>
      <Row label="Show token counts" hint="Display token usage per message"><Switch defaultChecked /></Row>
    </Panel>
  );
}

function AgentsSection() {
  const agents = [
    { name: "Atlas", role: "Strategist", model: "atlas-opus-4", enabled: true },
    { name: "Nova", role: "Coder", model: "nova-sonnet", enabled: true },
    { name: "Echo", role: "Writer", model: "echo-mini", enabled: true },
    { name: "Sage", role: "Researcher", model: "atlas-opus-4", enabled: false },
  ];
  return (
    <Panel title="Agents & models" desc="Configure which agents your team can use.">
      <div className="space-y-2">
        {agents.map((a) => (
          <div key={a.name} className="flex items-center gap-3 rounded-lg border border-border bg-surface-2/40 p-3">
            <div className="h-9 w-9 rounded-lg bg-gradient-to-br from-primary to-orange-500 grid place-items-center text-primary-foreground text-xs font-semibold">{a.name[0]}</div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium">{a.name} <span className="text-muted-foreground font-normal">· {a.role}</span></div>
              <div className="text-mono text-[11px] text-muted-foreground">{a.model}</div>
            </div>
            <Badge variant="secondary" className="text-[10px]">{a.enabled ? "Enabled" : "Off"}</Badge>
            <Switch defaultChecked={a.enabled} />
          </div>
        ))}
      </div>
      <Button variant="secondary" size="sm" className="mt-4">+ New agent</Button>
    </Panel>
  );
}

function ApiSection() {
  return (
    <Panel title="API keys" desc="Use these to authenticate programmatic access.">
      <div className="rounded-lg border border-border overflow-hidden">
        {[
          { name: "Production", key: "sk_live_••••••••••••7a92", used: "2 min ago" },
          { name: "Development", key: "sk_test_••••••••••••41c0", used: "3d ago" },
        ].map((k) => (
          <div key={k.name} className="flex items-center gap-3 px-4 py-3 border-b border-border last:border-0">
            <div className="flex-1">
              <div className="text-sm font-medium">{k.name}</div>
              <div className="text-mono text-[12px] text-muted-foreground">{k.key}</div>
            </div>
            <span className="text-[11px] text-muted-foreground">Used {k.used}</span>
            <Button variant="ghost" size="sm">Reveal</Button>
            <Button variant="ghost" size="sm" className="text-destructive">Revoke</Button>
          </div>
        ))}
      </div>
      <Button variant="secondary" size="sm" className="mt-4">+ Create key</Button>
    </Panel>
  );
}

function NotificationsSection() {
  return (
    <Panel title="Notifications" desc="Choose what pings you.">
      {["Mentions in shared chats", "Agent finishes long task", "Weekly usage digest", "Product updates", "Security alerts"].map((n, i) => (
        <Row key={n} label={n}><Switch defaultChecked={i < 3} /></Row>
      ))}
    </Panel>
  );
}

function SecuritySection() {
  return (
    <>
      <Panel title="Security" desc="Keep your account safe.">
        <Row label="Two-factor auth" hint="Require a code on every sign-in"><Switch defaultChecked /></Row>
        <Row label="Session timeout" hint="Auto sign-out after inactivity"><Input defaultValue="30 min" className="w-32" /></Row>
        <Row label="IP allowlist"><Button variant="secondary" size="sm">Configure</Button></Row>
      </Panel>
      <Panel title="Active sessions">
        <div className="space-y-2">
          {[
            { d: "MacBook Pro · Chrome", l: "San Francisco, US", now: true },
            { d: "iPhone 15 · Safari", l: "San Francisco, US", now: false },
          ].map((s) => (
            <div key={s.d} className="flex items-center gap-3 rounded-lg border border-border p-3">
              <div className="flex-1">
                <div className="text-sm">{s.d}</div>
                <div className="text-[11px] text-muted-foreground">{s.l}</div>
              </div>
              {s.now ? <Badge className="bg-success/20 text-success">This device</Badge> : <Button variant="ghost" size="sm" className="text-destructive">Sign out</Button>}
            </div>
          ))}
        </div>
      </Panel>
    </>
  );
}

function BillingSection() {
  return (
    <>
      <Panel title="Plan" desc="You're on the Pro plan.">
        <div className="rounded-lg border border-primary/40 bg-primary/5 p-4">
          <div className="flex items-baseline gap-2">
            <span className="text-display text-3xl">$49</span>
            <span className="text-muted-foreground text-sm">/ seat / month</span>
          </div>
          <div className="text-xs text-muted-foreground mt-1">Next invoice Nov 12 · 12 seats · $588</div>
          <div className="mt-4 flex gap-2">
            <Button size="sm" variant="secondary">Change plan</Button>
            <Button size="sm" variant="ghost">Cancel</Button>
          </div>
        </div>
      </Panel>
      <Panel title="Usage this month">
        {[
          { l: "Messages", v: "48,214 / 100k", p: 48 },
          { l: "Tokens", v: "1.2M / 5M", p: 24 },
          { l: "Storage", v: "42 GB / 250 GB", p: 17 },
        ].map((u) => (
          <div key={u.l} className="py-3 first:pt-0">
            <div className="flex justify-between text-sm mb-1"><span>{u.l}</span><span className="text-mono text-muted-foreground">{u.v}</span></div>
            <div className="h-1.5 rounded-full bg-surface-2 overflow-hidden"><div className="h-full bg-primary" style={{ width: `${u.p}%` }} /></div>
          </div>
        ))}
      </Panel>
    </>
  );
}

function IntegrationsSection() {
  const items = [
    { n: "Slack", d: "Post threads to a channel", on: true },
    { n: "GitHub", d: "Reference issues and PRs", on: true },
    { n: "Notion", d: "Sync docs into knowledge", on: false },
    { n: "Linear", d: "Turn chats into tickets", on: false },
    { n: "Google Drive", d: "Attach docs from Drive", on: true },
    { n: "Zapier", d: "Trigger flows from agents", on: false },
  ];
  return (
    <Panel title="Integrations" desc="Connect Atlas to the rest of your stack.">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {items.map((i) => (
          <div key={i.n} className="flex items-center gap-3 rounded-lg border border-border p-3">
            <div className="h-9 w-9 rounded-md bg-surface-2 grid place-items-center text-mono text-sm font-semibold">{i.n[0]}</div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium">{i.n}</div>
              <div className="text-[11px] text-muted-foreground truncate">{i.d}</div>
            </div>
            <Button variant={i.on ? "secondary" : "default"} size="sm" className={i.on ? "" : "bg-primary text-primary-foreground"}>{i.on ? "Manage" : "Connect"}</Button>
          </div>
        ))}
      </div>
    </Panel>
  );
}
