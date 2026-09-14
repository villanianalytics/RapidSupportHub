import { useEffect, useState } from "react";
import { Check, KeyRound, Plus, ShieldCheck } from "lucide-react";
import { api, Catalog, date, label, User } from "./api";
import { Field, Modal } from "./main";
import { SSOSettings } from "./sso";
import { EmailSettings } from "./mail";
import { RoutingSettings } from "./routing";

const roleOptions = [
  "admin",
  "agent",
  "developer",
  "assigner",
  "customer_own",
  "customer_company",
];
const defaultConfig = {
  timezone: "America/New_York",
  coverage: "24x7",
  weekdays: [0, 1, 2, 3, 4],
  start: "09:00",
  end: "17:00",
  holidays: [] as string[],
  pause_waiting: true,
  targets: [
    {
      severity: "sev1",
      incident_type: "*",
      first_response: 30,
      resolution: 240,
      reply: 60,
      update: 60,
    },
    {
      severity: "sev2",
      incident_type: "*",
      first_response: 120,
      resolution: 480,
      reply: 240,
      update: 240,
    },
    {
      severity: "sev3",
      incident_type: "*",
      first_response: 480,
      resolution: 2400,
      reply: null,
      update: null,
    },
    {
      severity: "sev4",
      incident_type: "*",
      first_response: 1440,
      resolution: 4800,
      reply: null,
      update: null,
    },
  ],
};
export function Admin({
  catalog,
  refresh,
  user,
  onHelp,
  onAudit,
}: {
  catalog: Catalog;
  refresh: () => Promise<void>;
  user: User;
  onHelp: (topic: string) => void;
  onAudit: () => void;
}) {
  const [tab, setTab] = useState("workspace"),
    [users, setUsers] = useState<User[]>([]),
    [policies, setPolicies] = useState<any[]>([]),
    [keys, setKeys] = useState<any[]>([]),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [token, setToken] = useState(""),
    [company, setCompany] = useState(""),
    [config, setConfig] = useState<any>(structuredClone(defaultConfig)),
    [policyName, setPolicyName] = useState("Standard support"),
    [editUser, setEditUser] = useState<User | null>(null),
    [resetUser, setResetUser] = useState<User | null>(null),
    [newRoles, setNewRoles] = useState<string[]>(["agent"]);
  async function load() {
    const [u, p, k] = await Promise.all([
      api<User[]>("/admin/users"),
      api("/admin/policies"),
      api("/admin/keys"),
    ]);
    setUsers(u);
    setPolicies(p);
    setKeys(k);
  }
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, []);
  async function execute(fn: () => Promise<any>, message: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
      await Promise.all([load(), refresh()]);
      setNotice(message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const tabs = [
    ["workspace", "Workspace"],
    ["users", "People & permissions"],
    ["sla", "SLA policies"],
    ["routing", "Categories & assignment"],
    ["api", "API access"],
    ["sso", "Single sign-on"],
    ["email", "Email delivery"],
  ];
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">MAKE IT YOURS</div>
          <h1>Workspace settings</h1>
          <p className="muted">
            The people, products, and promises behind your support.
          </p>
        </div>
        <span className="pill">
          <ShieldCheck size={14} /> ADMINISTRATOR
        </span>
      </div>
      <section
        className="panel admin-tools"
        aria-labelledby="admin-tools-title"
      >
        <div>
          <div className="eyebrow">ADMINISTRATOR TOOLS</div>
          <h2 id="admin-tools-title">Security and access</h2>
          <p className="muted">
            Review recorded activity or connect your Microsoft identity
            provider.
          </p>
        </div>
        <div className="admin-tool-actions">
          <button className="secondary" onClick={onAudit}>
            View audit logs
          </button>
          <button className="secondary" onClick={() => setTab("sso")}>
            Configure Microsoft Entra
          </button>
          <button className="secondary" onClick={() => setTab("email")}>
            Configure Amazon SES
          </button>
        </div>
      </section>
      <div className="tabs">
        {tabs.map(([id, name]) => (
          <button
            className={tab === id ? "active" : ""}
            key={id}
            onClick={() => {
              setTab(id);
              setError("");
              setNotice("");
            }}
          >
            {name}
          </button>
        ))}
      </div>
      <button
        className="text-button settings-help"
        onClick={() =>
          onHelp(
            {
              workspace: "workspace",
              users: "users",
              sla: "sla-config",
              routing: "workspace",
              api: "api",
              sso: "sso",
              email: "email",
            }[tab] || "workspace",
          )
        }
      >
        Help with {tabs.find((t) => t[0] === tab)?.[1]}
      </button>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <div className="success" role="status">
          <Check size={16} />
          {notice}
        </div>
      )}
      {tab === "sso" && <SSOSettings users={users} />}
      {tab === "email" && <EmailSettings />}
      {tab === "routing" && <RoutingSettings catalog={catalog} refresh={refresh} />}
      {tab === "workspace" && (
        <div className="settings-grid">
          {(["products", "companies"] as const).map((entity) => (
            <section className="panel description" key={entity}>
              <h2>
                {entity === "products"
                  ? "Products & projects"
                  : "Client companies"}
              </h2>
              <p className="muted">
                {entity === "products"
                  ? "Organize support and internal issues around your software."
                  : "Group customers and assign client-specific service levels."}
              </p>
              <div className="entity-list">
                {catalog[entity].map((item) => (
                  <div key={item.id}>
                    <span className="mini-avatar">
                      {item.name.slice(0, 2).toUpperCase()}
                    </span>
                    <strong>{item.name}</strong>
                    <small>#{item.id}</small>
                  </div>
                ))}
                {!catalog[entity].length && (
                  <p className="muted">None added yet.</p>
                )}
              </div>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const form = e.currentTarget,
                    f = new FormData(form);
                  execute(async () => {
                    await api("/admin/" + entity, "POST", {
                      name: f.get("name"),
                      description: f.get("description") || "",
                    });
                    form.reset();
                  }, "Added successfully.");
                }}
              >
                <Field
                  label={
                    entity === "products"
                      ? "Product / project name"
                      : "Company name"
                  }
                >
                  <input
                    name="name"
                    required
                    placeholder={
                      entity === "products"
                        ? "e.g. RapidCube"
                        : "e.g. Acme Inc."
                    }
                    maxLength={160}
                  />
                </Field>
                {entity === "products" && (
                  <Field label="Description">
                    <input
                      name="description"
                      placeholder="A short description"
                    />
                  </Field>
                )}
                <button className="primary" disabled={busy}>
                  <Plus size={16} />
                  Add {entity === "products" ? "product" : "company"}
                </button>
              </form>
            </section>
          ))}
        </div>
      )}
      {tab === "users" && (
        <>
          <section className="panel">
            <div className="panel-heading">
              <h2>People & automation users</h2>
              <span className="count">{users.length}</span>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Roles</th>
                    <th>Reports</th>
                    <th>Account</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id}>
                      <td>
                        <strong>{u.name}</strong>
                        <small>
                          {u.username} {u.email ? `· ${u.email}` : ""} {u.phone ? `· ${u.phone}` : ""} {u.automation ? "· Automation" : ""}
                        </small>
                      </td>
                      <td>
                        {u.roles.map(label).join(", ")}
                        <small>
                          {
                            catalog.companies.find((c) => c.id === u.company_id)
                              ?.name
                          }
                        </small>
                      </td>
                      <td>{u.manage_reports ? "Can manage" : "View shared"}</td>
                      <td>
                        {u.active ? "Active" : "Disabled"}
                        {u.must_change_password && !u.automation && (
                          <small>Password change required</small>
                        )}
                      </td>
                      <td>
                        <button
                          className="text-button"
                          onClick={() => setEditUser(structuredClone(u))}
                        >
                          Edit access
                        </button>
                        {!u.automation && u.id !== user.id && (
                          <button
                            className="text-button"
                            onClick={() => setResetUser(u)}
                          >
                            Password options
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          {resetUser && (
            <Modal
              title={`Password options · ${resetUser.name}`}
              onClose={() => setResetUser(null)}
            >
              <div className="description">
                <p className="muted">
                  Both options sign this user out and revoke their API
                  credentials. They must change their password at the next
                  login.
                </p>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    const f = new FormData(e.currentTarget);
                    execute(async () => {
                      await api(
                        `/admin/users/${resetUser.id}/reset-password`,
                        "POST",
                        { temporary_password: f.get("temporary") },
                      );
                      setResetUser(null);
                    }, "Temporary password set. Share it securely with the user.");
                  }}
                >
                  <Field label="New temporary password">
                    <input
                      name="temporary"
                      type="password"
                      required
                      minLength={12}
                      maxLength={256}
                      autoComplete="new-password"
                    />
                  </Field>
                  <button className="primary" disabled={busy}>
                    Reset password
                  </button>
                </form>
                <hr />
                <p>
                  Keep their current password and require a replacement at
                  sign-in.
                </p>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() =>
                    execute(async () => {
                      await api(
                        `/admin/users/${resetUser.id}/require-password-change`,
                        "POST",
                      );
                      setResetUser(null);
                    }, "Password change required at next login.")
                  }
                >
                  Require password change
                </button>
                {error && (
                  <div role="alert" className="error">
                    {error}
                  </div>
                )}
              </div>
            </Modal>
          )}
          {editUser && (
            <section className="panel description">
              <h2>Edit access · {editUser.name}</h2>
              <RolePicker
                roles={editUser.roles}
                onChange={(roles) => setEditUser({ ...editUser, roles })}
              />
              <div className="form-grid">
                <Field label="Full name"><input value={editUser.name} onChange={(e)=>setEditUser({...editUser,name:e.target.value})}/></Field>
                <Field label="Email"><input type="email" value={editUser.email} onChange={(e)=>setEditUser({...editUser,email:e.target.value})}/></Field>
                <Field label="Phone number"><input type="tel" value={editUser.phone||""} onChange={(e)=>setEditUser({...editUser,phone:e.target.value})}/></Field>
              </div>
              <Field label="Client company">
                <select
                  value={editUser.company_id || ""}
                  onChange={(e) =>
                    setEditUser({
                      ...editUser,
                      company_id: e.target.value
                        ? Number(e.target.value)
                        : null,
                    })
                  }
                >
                  <option value="">None (staff)</option>
                  {catalog.companies.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </Field>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={editUser.manage_reports}
                  onChange={(e) =>
                    setEditUser({
                      ...editUser,
                      manage_reports: e.target.checked,
                    })
                  }
                />
                Manage custom reports
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={editUser.active}
                  onChange={(e) =>
                    setEditUser({ ...editUser, active: e.target.checked })
                  }
                />
                Account active
              </label>
              <div className="inline-actions">
                <button
                  className="primary"
                  disabled={busy}
                  onClick={() =>
                    execute(async () => {
                      await api(`/admin/users/${editUser.id}`, "PATCH", {
                        roles: editUser.roles,
                        name: editUser.name,
                        email: editUser.email,
                        phone: editUser.phone,
                        company_id: editUser.company_id,
                        manage_reports: editUser.manage_reports,
                        active: editUser.active,
                      });
                      setEditUser(null);
                    }, "Permissions updated; existing credentials revoked.")
                  }
                >
                  Save access
                </button>
                <button className="secondary" onClick={() => setEditUser(null)}>
                  Cancel
                </button>
              </div>
            </section>
          )}
          <section className="panel description">
            <h2>Add a user</h2>
            <p className="muted">
              Customers need a company. Human users change their temporary
              password at first sign-in.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const form = e.currentTarget,
                  f = new FormData(form);
                execute(async () => {
                  await api("/admin/users", "POST", {
                    username: f.get("username"),
                    name: f.get("name"),
                    email: f.get("email"),
                    phone: f.get("phone"),
                    password: f.get("password"),
                    roles: newRoles,
                    company_id: f.get("company")
                      ? Number(f.get("company"))
                      : null,
                    manage_reports: f.get("reports") === "on",
                    automation: f.get("automation") === "on",
                  });
                  form.reset();
                  setNewRoles(["agent"]);
                }, "User created.");
              }}
            >
              <div className="form-grid">
                <Field label="Full name">
                  <input name="name" required />
                </Field>
                <Field label="Username">
                  <input name="username" required minLength={3} />
                </Field>
                <Field label="Email">
                  <input name="email" type="email" />
                </Field>
                <Field label="Phone number"><input name="phone" type="tel" /></Field>
                <Field label="Temporary password (12+ characters)">
                  <input
                    name="password"
                    type="password"
                    autoComplete="new-password"
                    minLength={12}
                    required
                  />
                </Field>
                <Field label="Client company">
                  <select name="company">
                    <option value="">None (staff)</option>
                    {catalog.companies.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
              <RolePicker roles={newRoles} onChange={setNewRoles} />
              <label className="checkbox">
                <input type="checkbox" name="reports" />
                Can create and share custom reports
              </label>
              <label className="checkbox">
                <input type="checkbox" name="automation" />
                Automation account (API only; interactive sign-in disabled)
              </label>
              <button className="primary" disabled={busy || !newRoles.length}>
                <Plus size={16} />
                Create user
              </button>
            </form>
          </section>
        </>
      )}
      {tab === "sla" && (
        <section className="panel description">
          <h2>Client service commitments</h2>
          <p className="muted">
            Targets are in working minutes. Optional reply and update targets
            can be left blank. Policy changes apply to new tickets; existing
            tickets keep their original calendar and active targets.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              execute(
                () =>
                  api("/admin/policies", "PUT", {
                    company_id: Number(company),
                    name: policyName,
                    config,
                  }),
                "SLA policy saved.",
              );
            }}
          >
            <div className="form-grid">
              <Field label="Client company">
                <select
                  required
                  value={company}
                  onChange={(e) => {
                    setCompany(e.target.value);
                    const p = policies.find(
                      (p) => p.company_id === Number(e.target.value),
                    );
                    setConfig(structuredClone(p?.config || defaultConfig));
                    setPolicyName(p?.name || "Standard support");
                  }}
                >
                  <option value="">Select a client</option>
                  {catalog.companies.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Policy name">
                <input
                  required
                  value={policyName}
                  onChange={(e) => setPolicyName(e.target.value)}
                />
              </Field>
              <Field label="Coverage">
                <select
                  value={config.coverage}
                  onChange={(e) =>
                    setConfig({ ...config, coverage: e.target.value })
                  }
                >
                  <option value="24x7">24 hours / 7 days</option>
                  <option value="business">Business hours</option>
                </select>
              </Field>
              <Field label="Timezone (IANA)">
                <input
                  required
                  value={config.timezone}
                  onChange={(e) =>
                    setConfig({ ...config, timezone: e.target.value })
                  }
                  placeholder="America/New_York"
                />
              </Field>
            </div>
            {config.coverage === "business" && (
              <>
                <div className="form-grid">
                  <Field label="Business day starts">
                    <input
                      type="time"
                      required
                      value={config.start}
                      onChange={(e) =>
                        setConfig({ ...config, start: e.target.value })
                      }
                    />
                  </Field>
                  <Field label="Business day ends">
                    <input
                      type="time"
                      required
                      value={config.end}
                      onChange={(e) =>
                        setConfig({ ...config, end: e.target.value })
                      }
                    />
                  </Field>
                </div>
                <div className="role-picker">
                  {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map(
                    (day, i) => (
                      <label className="checkbox" key={day}>
                        <input
                          type="checkbox"
                          checked={config.weekdays.includes(i)}
                          onChange={(e) =>
                            setConfig({
                              ...config,
                              weekdays: e.target.checked
                                ? [...config.weekdays, i]
                                : config.weekdays.filter(
                                    (n: number) => n !== i,
                                  ),
                            })
                          }
                        />
                        {day}
                      </label>
                    ),
                  )}
                </div>
                <Field label="Holidays (one YYYY-MM-DD per line)">
                  <textarea
                    value={config.holidays.join("\n")}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        holidays: e.target.value.split("\n"),
                      })
                    }
                    onBlur={() =>
                      setConfig({
                        ...config,
                        holidays: config.holidays.filter(Boolean),
                      })
                    }
                  />
                </Field>
              </>
            )}
            <label className="checkbox">
              <input
                type="checkbox"
                checked={config.pause_waiting}
                onChange={(e) =>
                  setConfig({ ...config, pause_waiting: e.target.checked })
                }
              />
              Pause SLA clocks while waiting on the customer
            </label>
            <div className="table-scroll">
              <table className="sla-editor">
                <thead>
                  <tr>
                    <th>Severity</th>
                    <th>SLA classification</th>
                    <th>First response</th>
                    <th>Resolution</th>
                    <th>Reply (optional)</th>
                    <th>Update (optional)</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {config.targets.map((t: any, i: number) => (
                    <tr key={i}>
                      <td>
                        <select
                          aria-label={`Severity ${i + 1}`}
                          value={t.severity}
                          onChange={(e) =>
                            setConfig({
                              ...config,
                              targets: config.targets.map(
                                (v: any, n: number) =>
                                  n === i
                                    ? { ...v, severity: e.target.value }
                                    : v,
                              ),
                            })
                          }
                        >
                          {["sev1", "sev2", "sev3", "sev4"].map((s) => (
                            <option key={s} value={s}>
                              {s.toUpperCase()}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <select
                          aria-label={`SLA classification ${i + 1}`}
                          value={t.incident_type}
                          onChange={(e) =>
                            setConfig({
                              ...config,
                              targets: config.targets.map(
                                (v: any, n: number) =>
                                  n === i
                                    ? { ...v, incident_type: e.target.value }
                                    : v,
                              ),
                            })
                          }
                        >
                          {["*", "outage", "bug", "question", "enhancement"].map(
                            (s) => (
                              <option key={s} value={s}>
                                {s === "*" ? "All types" : label(s)}
                              </option>
                            ),
                          )}
                        </select>
                      </td>
                      {["first_response", "resolution", "reply", "update"].map(
                        (metric) => (
                          <td key={metric}>
                            <input
                              aria-label={`${label(metric)} ${i + 1} minutes`}
                              type="number"
                              min="1"
                              max="525600"
                              required={[
                                "first_response",
                                "resolution",
                              ].includes(metric)}
                              value={t[metric] ?? ""}
                              placeholder="Off"
                              onChange={(e) =>
                                setConfig({
                                  ...config,
                                  targets: config.targets.map(
                                    (v: any, n: number) =>
                                      n === i
                                        ? {
                                            ...v,
                                            [metric]: e.target.value
                                              ? Number(e.target.value)
                                              : null,
                                          }
                                        : v,
                                  ),
                                })
                              }
                            />
                          </td>
                        ),
                      )}
                      <td>
                        <button
                          type="button"
                          className="text-button"
                          disabled={config.targets.length === 1}
                          onClick={() =>
                            setConfig({
                              ...config,
                              targets: config.targets.filter(
                                (_: any, n: number) => n !== i,
                              ),
                            })
                          }
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="inline-actions">
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  setConfig({
                    ...config,
                    targets: [
                      ...config.targets,
                      {
                        severity: "sev1",
                        incident_type: "outage",
                        first_response: 15,
                        resolution: 120,
                        reply: null,
                        update: null,
                      },
                    ],
                  })
                }
              >
                <Plus size={16} />
                Add target
              </button>
              <button className="primary" disabled={busy}>
                Save SLA policy
              </button>
            </div>
          </form>
        </section>
      )}
      {tab === "api" && (
        <>
          <section className="panel description">
            <h2>
              <KeyRound size={20} /> Automation credentials
            </h2>
            <p className="muted">
              Create an automation user under People & permissions, then issue a
              scoped key. Keys inherit that user’s data access and never grant
              administrator endpoints.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                execute(async () => {
                  const k = await api("/admin/keys", "POST", {
                    user_id: Number(f.get("user")),
                    name: f.get("name"),
                    scopes: f.getAll("scope"),
                    expires_days: Number(f.get("days")),
                  });
                  setToken(k.token);
                }, "Key created. Copy it now; it will not be shown again.");
              }}
            >
              <div className="form-grid">
                <Field label="Automation user">
                  <select name="user" required defaultValue="">
                    <option value="" disabled>
                      Select a user
                    </option>
                    {users
                      .filter((u) => u.automation && u.active)
                      .map((u) => (
                        <option key={u.id} value={u.id}>
                          {u.name}
                        </option>
                      ))}
                  </select>
                </Field>
                <Field label="Credential name">
                  <input
                    name="name"
                    required
                    placeholder="e.g. Release pipeline"
                  />
                </Field>
                <Field label="Expires after (days)">
                  <input
                    name="days"
                    type="number"
                    defaultValue={90}
                    min={1}
                    max={365}
                    required
                  />
                </Field>
              </div>
              <div className="role-picker">
                {["read", "write", "reports"].map((s) => (
                  <label className="checkbox" key={s}>
                    <input
                      type="checkbox"
                      name="scope"
                      value={s}
                      defaultChecked={s === "read"}
                    />
                    {label(s)}
                  </label>
                ))}
              </div>
              <button className="primary" disabled={busy}>
                Generate API key
              </button>
            </form>
            {token && (
              <div className="token-box">
                <strong>Copy your new key</strong>
                <code>{token}</code>
                <button className="secondary" onClick={() => setToken("")}>
                  I have saved it
                </button>
              </div>
            )}
            <p className="muted">
              Send <code>Authorization: Bearer YOUR_KEY</code> to REST
              endpoints.{" "}
              <a href="/api/docs" target="_blank" rel="noreferrer">
                Browse API documentation ↗
              </a>
            </p>
          </section>
          <section className="panel">
            <div className="panel-heading">
              <h2>Issued credentials</h2>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>User</th>
                    <th>Scopes</th>
                    <th>Expires</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {keys.map((k) => (
                    <tr key={k.id}>
                      <td>{k.name}</td>
                      <td>{users.find((u) => u.id === k.user_id)?.name}</td>
                      <td>{k.scopes.join(", ")}</td>
                      <td>{date(k.expires_at)}</td>
                      <td>
                        <button
                          className="text-button danger"
                          disabled={busy}
                          onClick={() =>
                            execute(
                              () => api(`/admin/keys/${k.id}`, "DELETE"),
                              "Credential revoked.",
                            )
                          }
                        >
                          Revoke
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </>
  );
}
function RolePicker({
  roles,
  onChange,
}: {
  roles: string[];
  onChange: (r: string[]) => void;
}) {
  return (
    <div className="role-picker">
      {roleOptions.map((r) => (
        <label className="checkbox" key={r}>
          <input
            type="checkbox"
            checked={roles.includes(r)}
            onChange={(e) =>
              onChange(
                e.target.checked ? [...roles, r] : roles.filter((v) => v !== r),
              )
            }
          />
          {label(r)}
        </label>
      ))}
    </div>
  );
}
