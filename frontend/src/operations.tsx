import { useEffect, useState } from "react";
import {
  Bell,
  Check,
  Clock3,
  Eye,
  Plus,
  Save,
  ShieldCheck,
} from "lucide-react";
import {
  api,
  Catalog,
  date,
  isStaff,
  label,
  statuses,
  Ticket,
  User,
} from "./api";
import { Field } from "./main";

export function Account({
  user,
  onChanged,
}: {
  user: User;
  onChanged: (user: User) => void;
}) {
  const [error, setError] = useState(""),
    [success, setSuccess] = useState(false),
    [busy, setBusy] = useState(false);
  if (user.auth_method === "entra")
    return (
      <section className="panel description account-panel">
        <h1>Account & security</h1>
        <p>Signed in with Microsoft as {user.name}.</p>
        <p>
          Your Microsoft password and multifactor authentication are managed by
          your organization. Portal roles and client access are managed by your
          support administrator.
        </p>
      </section>
    );
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">YOUR ACCOUNT</div>
          <h1>Account & security</h1>
          <p className="muted">
            {user.name} · {user.username}
          </p>
        </div>
        <ShieldCheck />
      </div>
      <section className="panel description account-panel">
        <h2>Change your password</h2>
        <p className="muted">
          Choose at least 12 characters. Changing your password signs out all
          other sessions and revokes your API credentials.
        </p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const form = e.currentTarget,
              f = new FormData(form);
            setError("");
            setSuccess(false);
            if (f.get("new") !== f.get("confirm")) {
              setError("The new passwords do not match.");
              return;
            }
            setBusy(true);
            try {
              const u = await api<User>("/auth/password", "POST", {
                current_password: f.get("current"),
                new_password: f.get("new"),
              });
              onChanged(u);
              form.reset();
              setSuccess(true);
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <Field label="Current password">
            <input
              type="password"
              name="current"
              autoComplete="current-password"
              required
            />
          </Field>
          <Field label="New password">
            <input
              type="password"
              name="new"
              autoComplete="new-password"
              minLength={12}
              maxLength={256}
              required
            />
          </Field>
          <Field label="Confirm new password">
            <input
              type="password"
              name="confirm"
              autoComplete="new-password"
              minLength={12}
              required
            />
          </Field>
          {error && (
            <div role="alert" className="error">
              {error}
            </div>
          )}
          {success && (
            <div role="status" className="success">
              <Check size={16} />
              Your password has been changed.
            </div>
          )}
          <button className="primary" disabled={busy}>
            Change password
          </button>
        </form>
      </section>
    </>
  );
}

export function Notifications({
  onOpen,
  onRead,
}: {
  onOpen: (id: number) => void;
  onRead: () => void;
}) {
  const [data, setData] = useState<any>({ items: [], unread_count: 0 }),
    [unread, setUnread] = useState(false),
    [offset, setOffset] = useState(0),
    [error, setError] = useState("");
  async function load() {
    try {
      setData(await api(`/notifications?unread=${unread}&offset=${offset}`));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    load();
    const timer = setInterval(load, 30000);
    return () => clearInterval(timer);
  }, [unread, offset]);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">STAY IN THE LOOP</div>
          <h1>Notifications</h1>
          <p className="muted">
            Assignments, conversations, and updates on the tickets you follow.
          </p>
        </div>
        <button
          className="secondary"
          onClick={async () => {
            try {
              await api("/notifications/read-all", "POST");
              await load();
              onRead();
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        >
          Mark all as read
        </button>
      </div>
      {error && <div className="error">{error}</div>}
      <section className="panel">
        <div className="panel-heading">
          <h2>
            <Bell size={18} />
            {data.unread_count} unread
          </h2>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={unread}
              onChange={(e) => {
                setUnread(e.target.checked);
                setOffset(0);
              }}
            />
            Unread only
          </label>
        </div>
        {data.items.map((n: any) => (
          <button
            key={n.id}
            className={`notification-row ${n.read_at ? "" : "unread"}`}
            onClick={async () => {
              try {
                await api(`/notifications/${n.id}`, "PATCH");
                onRead();
                onOpen(n.ticket_id);
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            <span className="notification-dot" />
            <div>
              <strong>{n.title}</strong>
              <small>
                #{String(n.ticket_id).padStart(4, "0")} · {label(n.kind)}
              </small>
            </div>
            <time>{date(n.created_at)}</time>
          </button>
        ))}
        {!data.items.length && (
          <div className="empty">
            <Bell />
            <h3>You’re all caught up.</h3>
            <p>New ticket activity will appear here.</p>
          </div>
        )}
        <div className="panel-footer">
          <span>
            Only activity on tickets you can currently access is shown.
          </span>
          <div>
            <button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 50))}
            >
              Previous
            </button>
            <button
              disabled={data.items.length < 50}
              onClick={() => setOffset(offset + 50)}
            >
              Next
            </button>
          </div>
        </div>
      </section>
    </>
  );
}

const attentionLabels: Record<string, string> = {
  breached: "SLA breached",
  at_risk: "SLA approaching",
  unanswered: "Needs a response",
  unassigned: "Unassigned",
};
export function Attention({ onOpen }: { onOpen: (id: number) => void }) {
  const [data, setData] = useState<any>({ items: [], total: 0, counts: {} }),
    [reason, setReason] = useState(""),
    [mine, setMine] = useState(false),
    [offset, setOffset] = useState(0),
    [error, setError] = useState("");
  useEffect(() => {
    async function load() {
      try {
        setData(
          await api(
            `/attention?reason=${reason}&mine=${mine}&offset=${offset}`,
          ),
        );
      } catch (e) {
        setError((e as Error).message);
      }
    }
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [reason, mine, offset]);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">FOCUS ON WHAT MATTERS</div>
          <h1>Attention needed</h1>
          <p className="muted">
            Live priorities, ordered by SLA urgency and age.
          </p>
        </div>
        <Clock3 />
      </div>
      {error && <div className="error">{error}</div>}
      <div className="stats attention-stats">
        {Object.entries(attentionLabels).map(([key, title]) => (
          <button
            key={key}
            className={`stat ${reason === key ? "chosen" : ""}`}
            onClick={() => {
              setReason(reason === key ? "" : key);
              setOffset(0);
            }}
          >
            <div>{title}</div>
            <strong>{data.counts[key] || 0}</strong>
            <small>
              {key === "at_risk"
                ? "At least 80% of the target elapsed"
                : "Click to filter this queue"}
            </small>
          </button>
        ))}
      </div>
      <section className="panel">
        <div className="panel-heading">
          <h2>{data.total} tickets need attention</h2>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={mine}
              onChange={(e) => {
                setMine(e.target.checked);
                setOffset(0);
              }}
            />
            Assigned to me
          </label>
        </div>
        {data.items.length ? (
          <div className="table-scroll">
            <table className="responsive-records attention-records">
              <thead>
                <tr>
                  <th>Ticket</th>
                  <th>Why it needs attention</th>
                  <th>Client / product</th>
                  <th>Assigned to</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((t: Ticket) => (
                  <tr key={t.id}>
                    <td className="record-title">
                      <button
                        className="ticket-title"
                        onClick={() => onOpen(t.id)}
                      >
                        {t.title}
                      </button>
                      <small>
                        #{t.id} · {date(t.created_at)}
                      </small>
                    </td>
                    <td data-label="Needs attention">
                      <div className="tag-list">
                        {t.attention?.map((r) => (
                          <span
                            className={`badge ${r === "breached" ? "danger" : ""}`}
                            key={r}
                          >
                            {attentionLabels[r]}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td data-label="Client / product">
                      {t.company}
                      <small>{t.product}</small>
                    </td>
                    <td data-label="Assigned to">{t.assignee}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty">
            <Check />
            <h3>No tickets need attention here.</h3>
          </div>
        )}
        <div className="panel-footer">
          <span>
            Closed and pending-approval tickets are excluded. A ticket can
            appear in multiple categories.
          </span>
          <div>
            <button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 100))}
            >
              Previous
            </button>
            <button
              disabled={offset + 100 >= data.total}
              onClick={() => setOffset(offset + 100)}
            >
              Next
            </button>
          </div>
        </div>
      </section>
    </>
  );
}

export function TicketExtras({
  ticket: t,
  user,
  catalog,
  onChange,
}: {
  ticket: Ticket;
  user: User;
  catalog: Catalog;
  onChange: (t: Ticket) => void;
}) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [tags, setTags] = useState((t.tags || []).join(", ")),
    [duplicate, setDuplicate] = useState(t.duplicate_of_id?.toString() || "");
  useEffect(() => {
    setTags((t.tags || []).join(", "));
    setDuplicate(t.duplicate_of_id?.toString() || "");
  }, [t.id, t.version]);
  async function action(fn: () => Promise<any>) {
    setBusy(true);
    setError("");
    try {
      await fn();
      onChange(await api(`/tickets/${t.id}`));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <section className="panel description">
        <h2>
          <Eye size={17} />
          Follow this ticket
        </h2>
        <p className="muted small">
          Watchers receive in-app updates. The creator and assignee are always
          notified.
        </p>
        <button
          className="secondary full"
          disabled={busy}
          onClick={() =>
            action(() =>
              api(
                `/tickets/${t.id}/watchers/${user.id}`,
                t.watching ? "DELETE" : "PUT",
              ),
            )
          }
        >
          {t.watching ? "Stop watching" : "Watch ticket"}
        </button>
        {isStaff(user) && (
          <>
            <div className="watcher-list">
              {t.watchers?.map((w) => (
                <div key={w.id}>
                  <span>{w.name}</span>
                  <button
                    className="text-button"
                    disabled={busy}
                    aria-label={`Remove watcher ${w.name}`}
                    onClick={() =>
                      action(() =>
                        api(`/tickets/${t.id}/watchers/${w.id}`, "DELETE"),
                      )
                    }
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
            <Field label="Add staff watcher">
              <select
                value=""
                disabled={busy}
                onChange={(e) => {
                  if (e.target.value)
                    action(() =>
                      api(`/tickets/${t.id}/watchers/${e.target.value}`, "PUT"),
                    );
                }}
              >
                <option value="">Select a colleague</option>
                {catalog.agents
                  .filter((a) => !t.watchers?.some((w) => w.id === a.id))
                  .map((a) => (
                    <option value={a.id} key={a.id}>
                      {a.name}
                    </option>
                  ))}
              </select>
            </Field>
          </>
        )}
      </section>
      {isStaff(user) && (
        <section className="panel description">
          <h2>Organization</h2>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              action(() =>
                api(`/tickets/${t.id}/organization`, "PATCH", {
                  version: t.version,
                  tags: tags.split(","),
                  duplicate_of_id: duplicate ? Number(duplicate) : null,
                }),
              );
            }}
          >
            <Field label="Tags (comma-separated)">
              <input
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="export, customer-impact"
              />
            </Field>
            <Field label="Duplicate of ticket ID">
              <input
                type="number"
                min={1}
                value={duplicate}
                onChange={(e) => setDuplicate(e.target.value)}
                placeholder="Original ticket ID"
              />
            </Field>
            <p className="muted small">
              Tags and duplicate links are staff-only. Linking preserves both
              tickets and their SLA history.
            </p>
            <button className="secondary full" disabled={busy}>
              Save organization
            </button>
          </form>
        </section>
      )}
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
    </>
  );
}

export function ViewTools({
  catalog,
  staff,
  filters,
  onFilters,
  layout,
  onLayout,
}: {
  catalog: Catalog;
  staff: boolean;
  filters: any;
  onFilters: (v: any) => void;
  layout: string;
  onLayout: (v: string) => void;
}) {
  const [views, setViews] = useState<any[]>([]),
    [active, setActive] = useState(""),
    [name, setName] = useState(""),
    [error, setError] = useState("");
  const load = () => api("/views").then(setViews);
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, []);
  function change(key: string, value: any) {
    onFilters({ ...filters, [key]: value });
    setActive("");
  }
  return (
    <div className="view-tools">
      <div className="advanced-filters">
        <select
          aria-label="Filter by severity"
          value={filters.severity || ""}
          onChange={(e) => change("severity", e.target.value)}
        >
          <option value="">All severities</option>
          {["sev1", "sev2", "sev3", "sev4"].map((s) => (
            <option key={s} value={s}>
              {label(s)}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by product"
          value={filters.product_id || ""}
          onChange={(e) =>
            change("product_id", e.target.value ? Number(e.target.value) : null)
          }
        >
          <option value="">All products</option>
          {catalog.products.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by client"
          value={filters.company_id || ""}
          onChange={(e) =>
            change("company_id", e.target.value ? Number(e.target.value) : null)
          }
        >
          <option value="">All clients</option>
          {catalog.companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        {staff && (
          <input
            aria-label="Filter by tag"
            value={filters.tag || ""}
            placeholder="Filter by tag"
            onChange={(e) => change("tag", e.target.value)}
          />
        )}
        <label className="checkbox">
          <input
            type="checkbox"
            checked={filters.watching || false}
            onChange={(e) => change("watching", e.target.checked)}
          />
          Watching
        </label>
      </div>
      <div className="saved-view-tools">
        <select
          aria-label="Saved view"
          value={active}
          onChange={(e) => {
            setActive(e.target.value);
            const v = views.find((v) => String(v.id) === e.target.value);
            if (v) {
              onFilters(v.config);
              onLayout(v.config.layout);
            }
          }}
        >
          <option value="">My saved views</option>
          {views.map((v) => (
            <option value={v.id} key={v.id}>
              {v.name}
            </option>
          ))}
        </select>
        {active && (
          <button
            className="text-button"
            onClick={async () => {
              try {
                await api(`/views/${active}`, "DELETE");
                setActive("");
                await load();
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            Delete view
          </button>
        )}
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setError("");
            try {
              const v = await api("/views", "POST", {
                name,
                config: { ...filters, layout },
              });
              await load();
              setActive(String(v.id));
              setName("");
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        >
          <input
            aria-label="View name"
            required
            value={name}
            maxLength={100}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name these filters"
          />
          <button className="secondary">
            <Save size={13} />
            Save view
          </button>
        </form>
      </div>
      {error && <div className="error">{error}</div>}
    </div>
  );
}

export function BulkActions({
  tickets,
  catalog,
  onComplete,
}: {
  tickets: Ticket[];
  catalog: Catalog;
  onComplete: () => void;
}) {
  const [status, setStatus] = useState(""),
    [assignee, setAssignee] = useState("unchanged"),
    [resolution, setResolution] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <div className="bulk-actions">
      <strong>{tickets.length} selected</strong>
      <select
        aria-label="Bulk status"
        value={status}
        onChange={(e) => setStatus(e.target.value)}
      >
        <option value="">Keep status</option>
        {statuses.map((s) => (
          <option key={s} value={s}>
            {label(s)}
          </option>
        ))}
      </select>
      <select
        aria-label="Bulk assignment"
        value={assignee}
        onChange={(e) => setAssignee(e.target.value)}
      >
        <option value="unchanged">Keep assignment</option>
        <option value="">Unassigned</option>
        {catalog.agents.map((a) => (
          <option key={a.id} value={a.id}>
            {a.name}
          </option>
        ))}
      </select>
      {["pending_approval", "closed"].includes(status) && (
        <input
          aria-label="Bulk resolution"
          value={resolution}
          onChange={(e) => setResolution(e.target.value)}
          placeholder="Resolution for selected tickets"
        />
      )}
      <button
        className="primary"
        disabled={busy || (!status && assignee === "unchanged")}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            await api("/tickets/bulk", "POST", {
              tickets: tickets.map((t) => ({ id: t.id, version: t.version })),
              ...(status ? { status } : {}),
              ...(assignee !== "unchanged"
                ? { assignee_id: assignee ? Number(assignee) : null }
                : {}),
              ...(resolution ? { resolution } : {}),
            });
            onComplete();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        Apply to selected
      </button>
      <span className="muted small">
        All selected tickets must pass validation; otherwise none are changed.
      </span>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}
