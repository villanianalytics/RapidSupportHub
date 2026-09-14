import { useEffect, useState } from "react";
import { BarChart3, Download, Play, Save } from "lucide-react";
import { api, Catalog, duration, label, statuses, User } from "./api";
import { Field } from "./main";
const reportColumns = [
  "id",
  "title",
  "description",
  "company",
  "product",
  "status",
  "severity",
  "incident_type",
  "assignee",
  "creator",
  "kind",
  "created_at",
  "updated_at",
  "resolution",
  "first_response_minutes",
  "resolution_minutes",
];
const defaultColumns = [
  "id",
  "title",
  "company",
  "product",
  "status",
  "severity",
  "assignee",
];
export function Reports({ user, catalog }: { user: User; catalog: Catalog }) {
  const canManage = user.roles.includes("admin") || user.manage_reports;
  const [saved, setSaved] = useState<any[]>([]),
    [config, setConfig] = useState<any>({
      group_by: "incident_type",
      metric: "first_response",
    }),
    [result, setResult] = useState<any>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [active, setActive] = useState<number | null>(null),
    [name, setName] = useState(""),
    [shared, setShared] = useState(false);
  const load = () => api("/reports").then(setSaved);
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, []);
  async function run(id?: number) {
    setError("");
    setBusy(true);
    try {
      setResult(
        await api(
          id ? `/reports/${id}/run` : "/reports/run",
          id ? "GET" : "POST",
          id ? undefined : config,
        ),
      );
      setActive(id || null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function filter(key: string, value: string, numeric = false) {
    setConfig({
      ...config,
      [key]: value ? (numeric ? Number(value) : value) : null,
    });
    setActive(null);
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">FROM DATA TO UNDERSTANDING</div>
          <h1>Reporting studio</h1>
          <p className="muted">
            Understand your response times, service commitments, and workload.
          </p>
        </div>
        <span className="pill">PERMISSION-AWARE DATA</span>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <div className="report-layout">
        <aside className="panel description saved-reports">
          <h2>Saved reports</h2>
          {saved.map((r) => (
            <div key={r.id}>
              <button
                className={
                  active === r.id ? "report-link active" : "report-link"
                }
                onClick={() => {
                  setConfig(r.config);
                  run(r.id);
                }}
              >
                <BarChart3 size={16} />
                <span>
                  {r.name}
                  <small>
                    {r.shared ? "Shared with workspace" : "Only you"}
                  </small>
                </span>
              </button>
              {canManage &&
                (r.owner_id === user.id || user.roles.includes("admin")) && (
                  <button
                    className="text-button small"
                    onClick={async () => {
                      try {
                        await api(`/reports/${r.id}`, "DELETE");
                        if (active === r.id) {
                          setActive(null);
                          setResult(null);
                        }
                        await load();
                      } catch (e) {
                        setError((e as Error).message);
                      }
                    }}
                  >
                    Delete
                  </button>
                )}
            </div>
          ))}
          {!saved.length && <p className="muted">No saved reports yet.</p>}
          <p className="small muted">
            Sharing a report never grants access to additional tickets.
          </p>
        </aside>
        <div>
          {canManage && (
            <section className="panel description">
              <h2>Build a report</h2>
              <Field label="Report layout">
                <select
                  value={config.view || "summary"}
                  onChange={(e) => filter("view", e.target.value)}
                >
                  <option value="summary">Grouped summary & metrics</option>
                  <option value="records">
                    Ticket records & selected columns
                  </option>
                </select>
              </Field>
              {config.view === "records" && (
                <div className="role-picker">
                  {reportColumns.map((column) => (
                    <label className="checkbox" key={column}>
                      <input
                        type="checkbox"
                        checked={(config.columns || defaultColumns).includes(
                          column,
                        )}
                        onChange={(e) => {
                          const columns = config.columns || defaultColumns;
                          setConfig({
                            ...config,
                            columns: e.target.checked
                              ? [...columns, column]
                              : columns.filter((c: string) => c !== column),
                          });
                        }}
                      />
                      {label(column)}
                    </label>
                  ))}
                </div>
              )}
              <div className="form-grid">
                <Field label="Measure">
                  <select
                    value={config.metric}
                    disabled={config.view === "records"}
                    onChange={(e) => filter("metric", e.target.value)}
                  >
                    {[
                      "count",
                      "first_response",
                      "resolution",
                      "reply",
                      "update",
                    ].map((s) => (
                      <option key={s} value={s}>
                        {s === "count" ? "Ticket count" : label(s)}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Group by">
                  <select
                    value={config.group_by}
                    disabled={config.view === "records"}
                    onChange={(e) => filter("group_by", e.target.value)}
                  >
                    {[
                      "incident_type",
                      "severity",
                      "assignee",
                      "first_response_agent",
                      "company",
                      "product",
                      "status",
                      "kind",
                    ].map((s) => (
                      <option key={s} value={s}>
                        {label(s)}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Client company">
                  <select
                    value={config.company_id || ""}
                    onChange={(e) => filter("company_id", e.target.value, true)}
                  >
                    <option value="">All accessible clients</option>
                    {catalog.companies.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Product / project">
                  <select
                    value={config.product_id || ""}
                    onChange={(e) => filter("product_id", e.target.value, true)}
                  >
                    <option value="">All products</option>
                    {catalog.products.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Status">
                  <select
                    value={config.status || ""}
                    onChange={(e) => filter("status", e.target.value)}
                  >
                    <option value="">All statuses</option>
                    {statuses.map((s) => (
                      <option key={s} value={s}>
                        {label(s)}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Severity">
                  <select
                    value={config.severity || ""}
                    onChange={(e) => filter("severity", e.target.value)}
                  >
                    <option value="">All severities</option>
                    {["sev1", "sev2", "sev3", "sev4"].map((s) => (
                      <option key={s} value={s}>
                        {label(s)}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Created from (UTC)">
                  <input
                    type="date"
                    value={config.from_date || ""}
                    onChange={(e) => filter("from_date", e.target.value)}
                  />
                </Field>
                <Field label="Created through (UTC)">
                  <input
                    type="date"
                    value={config.to_date || ""}
                    onChange={(e) => filter("to_date", e.target.value)}
                  />
                </Field>
                <Field label="Ticket kind">
                  <select
                    value={config.kind || ""}
                    onChange={(e) => filter("kind", e.target.value)}
                  >
                    <option value="">All accessible records</option>
                    <option value="support">Support tickets</option>
                    <option value="bug">Internal bugs</option>
                  </select>
                </Field>
                <Field label="Incident type">
                  <select
                    value={config.incident_type || ""}
                    onChange={(e) => filter("incident_type", e.target.value)}
                  >
                    <option value="">All incident types</option>
                    {["outage", "bug", "question", "enhancement"].map((s) => (
                      <option key={s} value={s}>
                        {label(s)}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Assigned agent">
                  <select
                    value={config.assignee_id || ""}
                    onChange={(e) =>
                      filter("assignee_id", e.target.value, true)
                    }
                  >
                    <option value="">All agents</option>
                    {catalog.agents.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
              <button className="primary" disabled={busy} onClick={() => run()}>
                <Play size={15} />
                {busy ? "Running…" : "Run report"}
              </button>
              <form
                className="save-report"
                onSubmit={async (e) => {
                  e.preventDefault();
                  setBusy(true);
                  setError("");
                  try {
                    await api("/reports", "POST", { name, shared, config });
                    await load();
                    setName("");
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                <input
                  aria-label="Report name"
                  placeholder="Name this report"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  maxLength={160}
                />
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={shared}
                    onChange={(e) => setShared(e.target.checked)}
                  />
                  Share
                </label>
                <button className="secondary" disabled={busy}>
                  <Save size={15} />
                  Save
                </button>
              </form>
            </section>
          )}
          {result ? (
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>
                    {result.view === "records"
                      ? "Ticket records"
                      : `${label(result.metric)} by ${label(result.group_by).toLowerCase()}`}
                  </h2>
                  <p className="muted">
                    {result.total_tickets} accessible tickets
                  </p>
                </div>
                {active && (
                  <a
                    className="secondary"
                    href={`/api/reports/${active}/run?export=true`}
                  >
                    <Download size={16} />
                    CSV
                  </a>
                )}
              </div>
              {result.rows.length && result.view === "records" ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        {result.columns.map((column: string) => (
                          <th key={column}>{label(column)}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.rows.map((row: any, index: number) => (
                        <tr key={index}>
                          {result.columns.map((column: string) => (
                            <td key={column}>
                              {row[column] === null ? "—" : String(row[column])}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : result.rows.length ? (
                <>
                  <div className="report-chart">
                    {result.rows.map((r: any) => (
                      <div key={r.group}>
                        <span>{label(r.group)}</span>
                        <div>
                          <i
                            style={{
                              width: `${Math.max(1, ((result.metric === "count" ? r.tickets : r.average_minutes || 0) / Math.max(1, ...result.rows.map((v: any) => (result.metric === "count" ? v.tickets : v.average_minutes || 0)))) * 100)}%`,
                            }}
                          />
                        </div>
                        <strong>
                          {result.metric === "count"
                            ? r.tickets
                            : duration(r.average_minutes)}
                        </strong>
                      </div>
                    ))}
                  </div>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>{label(result.group_by)}</th>
                          <th>Tickets</th>
                          {result.metric !== "count" && (
                            <>
                              <th>Completed / open</th>
                              <th>Average</th>
                              <th>Median</th>
                              <th>P90</th>
                              <th>Compliance</th>
                              <th>Breaches</th>
                            </>
                          )}
                        </tr>
                      </thead>
                      <tbody>
                        {result.rows.map((r: any) => (
                          <tr key={r.group}>
                            <td>{label(r.group)}</td>
                            <td>{r.tickets}</td>
                            {result.metric !== "count" && (
                              <>
                                <td>
                                  {r.completed} / {r.open}
                                </td>
                                <td>{duration(r.average_minutes)}</td>
                                <td>{duration(r.median_minutes)}</td>
                                <td>{duration(r.p90_minutes)}</td>
                                <td>
                                  {r.compliance_percent === null
                                    ? "—"
                                    : r.compliance_percent + "%"}
                                </td>
                                <td>{r.breached}</td>
                              </>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : (
                <div className="empty">
                  <BarChart3 size={30} />
                  <h3>No matching data</h3>
                  <p>
                    Try a different filter or add tickets to your workspace.
                  </p>
                </div>
              )}
              <p className="report-note">{result.note}</p>
            </section>
          ) : (
            <section className="panel empty">
              <BarChart3 size={32} />
              <h3>Your next insight starts here.</h3>
              <p>
                {canManage
                  ? "Choose a measure and run your report."
                  : "Select a shared report, or ask your administrator to create one."}
              </p>
            </section>
          )}
        </div>
      </div>
    </>
  );
}
