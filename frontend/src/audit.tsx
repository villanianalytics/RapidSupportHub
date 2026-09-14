import { useEffect, useRef, useState } from "react";
import { api } from "./api";

type Event = {
  id: number;
  created_at: string;
  actor: string;
  actor_id: number | null;
  action: string;
  outcome: string;
  resource: string;
  resource_id: string;
  request_id: string;
  auth_method: string;
  credential_id: number | null;
  ip: string;
  method: string;
  route: string;
  status: number | null;
  details: Record<string, unknown>;
};
const empty = {
  q: "",
  action: "",
  resource: "",
  resource_id: "",
  actor_id: "",
  outcome: "",
  request_id: "",
  since: "",
  until: "",
};
export function AuditCenter() {
  const snapshot = useRef(0);
  const [filters, setFilters] = useState(empty),
    [applied, setApplied] = useState(empty);
  const [offset, setOffset] = useState(0),
    [revision, setRevision] = useState(0);
  const [data, setData] = useState<{ items: Event[]; total: number }>({
    items: [],
    total: 0,
  });
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [selected, setSelected] = useState<Event | null>(null);
  function params(values: typeof empty) {
    return new URLSearchParams(
      Object.fromEntries(
        Object.entries(values)
          .filter(([, v]) => v)
          .map(([k, v]) => [
            k,
            k === "since" || k === "until" ? new Date(v).toISOString() : v,
          ]),
      ),
    );
  }
  useEffect(() => {
    let active = true;
    setBusy(true);
    setError("");
    api(
      `/admin/audit?${params(applied)}&offset=${offset}&snapshot=${snapshot.current}`,
    )
      .then((result) => {
        if (active) {
          setData(result);
          snapshot.current = result.snapshot;
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [applied, offset, revision]);
  async function download() {
    setError("");
    try {
      const response = await fetch(
        `/api/admin/audit?${params(applied)}&export=true&snapshot=${snapshot.current}`,
        { credentials: "include" },
      );
      if (!response.ok) {
        const body = await response.json();
        throw new Error(body.detail || "Export failed");
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "audit-events.csv";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <div className="audit-center">
      <div className="page-heading">
        <div>
          <div className="eyebrow">ACCOUNTABILITY & HISTORY</div>
          <h1>Audit center</h1>
          <p className="muted">
            Review activity, investigate changes, and trace a request across the
            system.
          </p>
        </div>
        <button className="secondary" disabled={busy} onClick={download}>
          Export filtered CSV
        </button>
      </div>
      <form
        className="panel audit-filters"
        onSubmit={(e) => {
          e.preventDefault();
          snapshot.current = 0;
          setApplied({ ...filters });
          setOffset(0);
          setSelected(null);
        }}
      >
        {Object.entries({
          q: "Search actor, action, resource or IP",
          action: "Exact action",
          resource: "Resource type",
          resource_id: "Resource ID",
          actor_id: "Actor user ID",
          request_id: "Request ID",
          since: "From (local time)",
          until: "Through (local time)",
        }).map(([key, label]) => (
          <label key={key}>
            {label}
            <input
              type={
                key === "since" || key === "until"
                  ? "datetime-local"
                  : key === "actor_id"
                    ? "number"
                    : "text"
              }
              min={key === "actor_id" ? "1" : undefined}
              value={filters[key as keyof typeof empty]}
              onChange={(e) =>
                setFilters({ ...filters, [key]: e.target.value })
              }
            />
          </label>
        ))}
        <label>
          Outcome
          <select
            value={filters.outcome}
            onChange={(e) =>
              setFilters({ ...filters, outcome: e.target.value })
            }
          >
            <option value="">All outcomes</option>
            {["success", "denied", "failure", "started"].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <div className="audit-filter-actions">
          <button className="primary" disabled={busy}>
            Apply filters
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              snapshot.current = 0;
              setFilters(empty);
              setApplied(empty);
              setOffset(0);
              setSelected(null);
              setRevision((v) => v + 1);
            }}
          >
            Reset / refresh
          </button>
        </div>
      </form>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <p className="muted" role="status">
        {busy
          ? "Loading audit events…"
          : `${data.total.toLocaleString()} events · newest first`}
      </p>
      {selected && (
        <section className="panel audit-detail">
          <button className="text-button" onClick={() => setSelected(null)}>
            Close event details
          </button>
          <h2>
            Event #{selected.id}: {selected.action}
          </h2>
          <p>
            {selected.actor} · {selected.auth_method} · Credential{" "}
            {selected.credential_id ?? "—"} · {selected.ip || "IP unavailable"}
          </p>
          <p>
            {selected.method} {selected.route} · HTTP {selected.status ?? "—"}
          </p>
          <p>Request: {selected.request_id}</p>
          <button
            className="secondary"
            onClick={() => {
              const next = { ...empty, request_id: selected.request_id };
              snapshot.current = 0;
              setFilters(next);
              setApplied(next);
              setOffset(0);
            }}
          >
            Show correlated events
          </button>
          <h3>Recorded details</h3>
          <pre>{JSON.stringify(selected.details, null, 2)}</pre>
        </section>
      )}
      <div className="audit-events">
        {data.items.map((row) => (
          <button
            className="panel audit-event"
            key={row.id}
            onClick={() => setSelected(row)}
          >
            <span className="audit-event-top">
              <strong>{row.action}</strong>
              <span className="badge">{row.outcome}</span>
            </span>
            <span>
              {row.actor} {row.actor_id ? `(#${row.actor_id})` : ""} ·{" "}
              {new Date(row.created_at + "Z").toLocaleString()}
            </span>
            <span className="muted">
              {row.resource || "Request"}
              {row.resource_id ? ` #${row.resource_id}` : ""} · Event #{row.id}
            </span>
          </button>
        ))}
      </div>
      {!busy && !data.items.length && (
        <div className="panel empty">No audit events match these filters.</div>
      )}
      <div className="audit-pagination">
        <button
          className="secondary"
          disabled={busy || offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 50))}
        >
          Previous events
        </button>
        <span>
          {data.total ? offset + 1 : 0}–{Math.min(offset + 50, data.total)} of{" "}
          {data.total}
        </span>
        <button
          className="secondary"
          disabled={busy || offset + 50 >= data.total}
          onClick={() => setOffset(offset + 50)}
        >
          Next events
        </button>
      </div>
      <p className="help-footnote">
        Administrator access only. Events are append-only and retained without
        automatic pruning. Results stay fixed while paging; use Reset / refresh
        for new activity. Request starts are recorded separately; correlate by
        request ID. Passwords and tokens are redacted; long conversation fields
        retain change metadata rather than their contents. Historical entries
        have limited metadata. Health checks, static files, and actions outside
        the application are not captured.
      </p>
    </div>
  );
}
