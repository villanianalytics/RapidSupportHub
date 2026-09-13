import React, { useState, useEffect, useCallback, useRef } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  Bell,
  Bug,
  Check,
  ChevronRight,
  CircleHelp,
  Clock3,
  Inbox,
  LayoutDashboard,
  LayoutGrid,
  List,
  LogOut,
  Menu,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Ticket as TicketIcon,
  X,
} from "lucide-react";
import {
  api,
  SessionChangedError,
  Catalog,
  date,
  duration,
  isStaff,
  label,
  statuses,
  Ticket,
  User,
} from "./api";
import { Admin } from "./settings";
import { Reports } from "./reports";
import { MicrosoftSignIn } from "./sso";
import {
  Account,
  Notifications,
  Attention,
  TicketExtras,
  ViewTools,
  BulkActions,
} from "./operations";
import "./styles.css";

export function Field({
  label: caption,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  const id = React.useId();
  return (
    <div className="field">
      <label htmlFor={id}>{caption}</label>
      {React.isValidElement(children)
        ? React.cloneElement(children as React.ReactElement<{ id: string }>, {
            id,
          })
        : children}
    </div>
  );
}
export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);
  return (
    <div
      className="overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header>
          <h2>{title}</h2>
          <button
            className="icon-button"
            aria-label="Close dialog"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}

function Auth({
  onLogin,
  user,
}: {
  onLogin: (u: User) => void;
  user: User | null;
}) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <div className="auth">
      <div className="auth-story">
        <div className="brand">
          <span className="brand-icon">
            <Activity />
          </span>
          RapidSupportHub
        </div>
        <div>
          <div className="eyebrow">A CLEARER PATH TO RESOLUTION</div>
          <h1>
            Good support.
            <br />
            Better software.
          </h1>
          <p>
            One place for your customers, your team, and every issue in between.
          </p>
          <div className="auth-decoration">
            <div>
              <Check /> Connected conversations
            </div>
            <div>
              <Clock3 /> Accountable response times
            </div>
            <div>
              <Bug /> A direct line to development
            </div>
          </div>
        </div>
        <small>Open source. Built around your team.</small>
      </div>
      <div className="auth-form">
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setError("");
            setBusy(true);
            const f = new FormData(e.currentTarget);
            try {
              onLogin(
                await api(
                  user ? "/auth/password" : "/auth/login",
                  "POST",
                  user
                    ? {
                        current_password: f.get("current"),
                        new_password: f.get("password"),
                      }
                    : {
                        username: f.get("username"),
                        password: f.get("password"),
                      },
                ),
              );
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <span className="pill">YOUR SUPPORT WORKSPACE</span>
          <h2>{user ? "Choose your new password" : "Welcome back."}</h2>
          <p className="muted">
            {user
              ? "Replace your temporary password to secure your account."
              : "Sign in to keep things moving."}
          </p>
          {user ? (
            <Field label="Current password">
              <input
                type="password"
                name="current"
                autoComplete="current-password"
                required
              />
            </Field>
          ) : (
            <Field label="Username">
              <input
                name="username"
                autoComplete="username"
                placeholder="Your username"
                required
                autoFocus
              />
            </Field>
          )}
          <Field
            label={user ? "New password · at least 12 characters" : "Password"}
          >
            <input
              type="password"
              name="password"
              autoComplete={user ? "new-password" : "current-password"}
              minLength={user ? 12 : undefined}
              required
            />
          </Field>
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <button className="primary full" disabled={busy}>
            {busy ? "Please wait…" : user ? "Save password" : "Sign in"}
            <ArrowRight size={17} />
          </button>
          <p className="auth-help">
            <ShieldCheck size={16} />{" "}
            {user
              ? "All existing sessions will be replaced."
              : "Need access? Contact your support administrator."}
          </p>
          {!user && <MicrosoftSignIn />}
        </form>
      </div>
    </div>
  );
}

function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null),
    drawer = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!menuOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const elements = () =>
      Array.from(
        drawer.current?.querySelectorAll<HTMLElement>("a,button") || [],
      ).filter((e) => e.getClientRects().length && !e.hasAttribute("disabled"));
    elements()[0]?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenuOpen(false);
        return;
      }
      if (e.key === "Tab") {
        const list = elements(),
          first = list[0],
          last = list[list.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    const resize = () => {
      if (innerWidth > 850) setMenuOpen(false);
    };
    document.addEventListener("keydown", key);
    window.addEventListener("resize", resize);
    return () => {
      document.body.style.overflow = previous;
      document.removeEventListener("keydown", key);
      window.removeEventListener("resize", resize);
      menuButton.current?.focus();
    };
  }, [menuOpen]);
  const [requestedStatus, setRequestedStatus] = useState<string | undefined>();
  const [user, setUser] = useState<User | null>(null),
    [loading, setLoading] = useState(true),
    [page, setPage] = useState("overview"),
    [catalog, setCatalog] = useState<Catalog>({
      products: [],
      companies: [],
      agents: [],
    }),
    [tickets, setTickets] = useState<Ticket[]>([]),
    [counts, setCounts] = useState<Record<string, number>>({}),
    [selected, setSelected] = useState<Ticket | null>(null),
    [create, setCreate] = useState(false),
    [view, setView] = useState("list"),
    [search, setSearch] = useState(""),
    [status, setStatus] = useState(""),
    [mine, setMine] = useState(false),
    [filters, setFilters] = useState<any>({}),
    [checked, setChecked] = useState<number[]>([]),
    [unread, setUnread] = useState(0),
    [offset, setOffset] = useState(0),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    if (!user || user.must_change_password) return;
    try {
      const [c, t, o] = await Promise.all([
        api<Catalog>("/catalog"),
        api<Ticket[]>(
          `/tickets?q=${encodeURIComponent(search)}&kind=${page === "bugs" ? "bug" : page === "tickets" ? "support" : ""}&status=${status}&mine=${mine}&offset=${offset}&${new URLSearchParams(
            Object.entries(filters)
              .filter(
                ([k, v]) =>
                  [
                    "severity",
                    "product_id",
                    "company_id",
                    "tag",
                    "watching",
                  ].includes(k) &&
                  v !== null &&
                  v !== undefined &&
                  v !== "",
              )
              .map(([k, v]) => [k, String(v)]),
          )}`,
        ),
        api("/reports/overview"),
      ]);
      setCatalog(c);
      setTickets(t);
      setCounts(
        Object.fromEntries(o.rows.map((r: any) => [r.group, r.tickets])),
      );
    } catch (e) {
      if (e instanceof SessionChangedError) return;
      setError((e as Error).message);
    }
  }, [user, page, search, status, mine, offset, filters]);
  const refreshUnread = useCallback(() => {
    if (user && !user.must_change_password)
      api("/notifications?unread=true")
        .then((n) => setUnread(n.unread_count))
        .catch(() => {});
  }, [user]);
  useEffect(() => {
    refreshUnread();
    const id = setInterval(refreshUnread, 30000);
    return () => clearInterval(id);
  }, [refreshUnread]);
  useEffect(
    () => setChecked([]),
    [page, search, status, mine, offset, filters],
  );
  useEffect(() => {
    api<User>("/auth/me")
      .then(setUser)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    const ended = () => {
      setUser(null);
      setMenuOpen(false);
      setSelected(null);
      setUnread(0);
      setError("");
    };
    window.addEventListener("rsh:session-ended", ended);
    return () => window.removeEventListener("rsh:session-ended", ended);
  }, []);
  useEffect(() => {
    const timeout = setTimeout(refresh, 180);
    return () => clearTimeout(timeout);
  }, [refresh]);
  useEffect(() => {
    if (!user) return;
    const id = setInterval(refresh, 60000);
    return () => clearInterval(id);
  }, [user, refresh]);
  async function open(id: number, targetStatus?: string) {
    try {
      setSelected(await api<Ticket>(`/tickets/${id}`));
      setRequestedStatus(targetStatus);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function move(t: Ticket, to: string) {
    if (to === t.status) return;
    if (to === "pending_approval" || (to === "closed" && t.kind === "bug")) {
      await open(t.id, to);
      return;
    }
    setBusy(true);
    try {
      await api(`/tickets/${t.id}`, "PATCH", {
        version: t.version,
        status: to,
      });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (loading) return <div className="loading">Opening your workspace…</div>;
  if (!user || user.must_change_password)
    return (
      <Auth
        user={user}
        onLogin={(next) => {
          setUser(next);
          setPage("overview");
          setSelected(null);
          setTickets([]);
          setCounts({});
          setCatalog({ products: [], companies: [], agents: [] });
          setFilters({});
          setSearch("");
          setStatus("");
          setMine(false);
          setOffset(0);
          setUnread(0);
          setError("");
        }}
      />
    );
  const staff = isStaff(user),
    isAdmin = user.roles.includes("admin"),
    total = Object.values(counts).reduce((a, b) => a + b, 0),
    openCount = total - (counts.closed || 0),
    risky = tickets.filter((t) =>
      t.sla?.some(
        (s) => ["at_risk", "breached"].includes(s.state) && !s.completed_at,
      ),
    ).length;
  const nav: [string, string, typeof Inbox][] = [
    ["overview", "Overview", LayoutDashboard],
    ["tickets", staff ? "Support tickets" : "My support", Inbox],
  ];
  if (staff) nav.push(["bugs", "Issue tracker", Bug]);
  if (staff) nav.push(["attention", "Attention needed", Clock3]);
  nav.push(
    ["notifications", "Notifications", Bell],
    ["account", "My account", ShieldCheck],
  );
  nav.push(["reports", "Reports", BarChart3]);
  if (isAdmin) nav.push(["settings", "Settings", Settings]);
  function navigate(p: string) {
    setMenuOpen(false);
    setPage(p);
    setSelected(null);
    setStatus("");
    setSearch("");
    setMine(false);
    setOffset(0);
    setFilters({});
  }
  return (
    <div className="shell">
      {menuOpen && (
        <button
          className="nav-backdrop"
          aria-label="Close navigation"
          onClick={() => setMenuOpen(false)}
        />
      )}
      <aside
        ref={drawer}
        id="workspace-navigation"
        className={`sidebar ${menuOpen ? "navigation-open" : ""}`}
      >
        <button
          className="mobile-menu-close icon-button"
          aria-label="Close menu"
          onClick={() => setMenuOpen(false)}
        >
          <X size={22} />
        </button>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("overview");
          }}
        >
          <span className="brand-icon">
            <Activity size={23} />
          </span>
          <span>
            Rapid<span className="brand-light">SupportHub</span>
          </span>
        </a>
        <div className="workspace-label">
          WORKSPACE <span>v0.3</span>
        </div>
        <nav>
          {nav.map(([key, text, Icon]) => (
            <button
              key={key}
              aria-label={text}
              title={text}
              className={page === key ? "nav-item active" : "nav-item"}
              onClick={() => navigate(key)}
            >
              <Icon size={19} />
              <span>{text}</span>
              {key === "tickets" && openCount > 0 && <b>{openCount}</b>}
              {key === "notifications" && unread > 0 && <b>{unread}</b>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="portal-status">
            <span className="live-dot" /> Portal is live
            <small>Email integration · coming later</small>
          </div>
          <div className="profile">
            <span className="avatar">
              {user.name.slice(0, 2).toUpperCase()}
            </span>
            <div>
              <strong>{user.name}</strong>
              <small>{label(user.roles[0])}</small>
            </div>
            <button
              aria-label="Sign out"
              className="icon-button"
              onClick={async () => {
                await api("/auth/logout", "POST");
                setUser(null);
                setSelected(null);
                setMenuOpen(false);
              }}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <main inert={menuOpen}>
        <header className="topbar">
          <div>
            <button
              ref={menuButton}
              className="mobile-menu-button icon-button"
              aria-label="Open navigation"
              aria-expanded={menuOpen}
              aria-controls="workspace-navigation"
              onClick={() => setMenuOpen(true)}
            >
              <Menu size={23} />
            </button>
            <span className="muted">Workspace</span>
            <ChevronRight size={14} />
            <strong>{nav.find((n) => n[0] === page)?.[1]}</strong>
          </div>
          <div className="topbar-right">
            <span className="local-date">
              {new Date().toLocaleDateString([], {
                weekday: "short",
                month: "short",
                day: "numeric",
              })}
            </span>
            <a
              href="/api/docs"
              target="_blank"
              rel="noreferrer"
              aria-label="REST API documentation"
            >
              <CircleHelp size={19} />
            </a>
          </div>
        </header>
        <div className="content">
          {error && (
            <div className="error" role="alert">
              {error}
              <button onClick={() => setError("")} aria-label="Dismiss error">
                <X size={16} />
              </button>
            </div>
          )}
          {selected ? (
            <TicketDetail
              ticket={selected}
              requestedStatus={requestedStatus}
              user={user}
              catalog={catalog}
              onBack={() => setSelected(null)}
              onChange={(t) => {
                setSelected(t);
                setRequestedStatus(undefined);
                refresh();
              }}
            />
          ) : page === "account" ? (
            <Account user={user} onChanged={setUser} />
          ) : page === "notifications" ? (
            <Notifications onOpen={open} onRead={refreshUnread} />
          ) : page === "attention" ? (
            <Attention onOpen={open} />
          ) : page === "settings" ? (
            <Admin catalog={catalog} refresh={refresh} user={user} />
          ) : page === "reports" ? (
            <Reports user={user} catalog={catalog} />
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">
                    {page === "overview"
                      ? "THE BIG PICTURE"
                      : page === "bugs"
                        ? "BUILD BETTER, TOGETHER"
                        : "EVERY CONVERSATION COUNTS"}
                  </div>
                  <h1>
                    {page === "overview"
                      ? `Your support, at a glance.`
                      : page === "bugs"
                        ? "Issue tracker"
                        : "Support tickets"}
                  </h1>
                  <p className="muted">
                    {page === "overview"
                      ? "A little clarity for your day. Here’s where things stand."
                      : page === "bugs"
                        ? "From the first reproduction to the final fix."
                        : "Keep your customers informed and your work moving."}
                  </p>
                </div>
                <button className="primary" onClick={() => setCreate(true)}>
                  <Plus size={18} />
                  {page === "bugs" ? "Log an issue" : "New ticket"}
                </button>
              </div>
              {page === "overview" && (
                <div className="stats">
                  <Stat
                    title="Open tickets & issues"
                    value={openCount}
                    icon={<Inbox />}
                    note="Across your accessible workspace"
                  />
                  <Stat
                    title="In progress"
                    value={counts.in_progress || 0}
                    icon={<Activity />}
                    note="Moving toward a resolution"
                  />
                  <Stat
                    title="Awaiting approval"
                    value={counts.pending_approval || 0}
                    icon={<ShieldCheck />}
                    note="Ready for the customer’s review"
                  />
                  <Stat
                    title="Closed"
                    value={counts.closed || 0}
                    icon={<Check />}
                    note="Resolutions delivered"
                  />
                </div>
              )}
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>
                      {page === "overview"
                        ? "The work ahead"
                        : page === "bugs"
                          ? "Project issues"
                          : "Ticket workspace"}{" "}
                      <span className="count">
                        {tickets.length}
                        {tickets.length === 100 ? "+" : ""}
                      </span>
                    </h2>
                    {staff && risky > 0 && (
                      <p className="risk-caption">
                        <Clock3 size={14} />
                        {risky} visible ticket{risky > 1 ? "s" : ""} need SLA
                        attention
                      </p>
                    )}
                  </div>
                  <div className="segmented">
                    <button
                      className={view === "list" ? "selected" : ""}
                      aria-label="List view"
                      onClick={() => setView("list")}
                    >
                      <List size={16} />
                      List
                    </button>
                    <button
                      className={view === "board" ? "selected" : ""}
                      aria-label="Kanban view"
                      onClick={() => setView("board")}
                    >
                      <LayoutGrid size={16} />
                      Board
                    </button>
                  </div>
                </div>
                <div className="toolbar">
                  <div className="search">
                    <Search size={17} />
                    <input
                      aria-label="Search tickets"
                      placeholder="Search ticket titles…"
                      value={search}
                      onChange={(e) => {
                        setSearch(e.target.value);
                        setOffset(0);
                      }}
                    />
                  </div>
                  <select
                    aria-label="Filter by status"
                    value={status}
                    onChange={(e) => {
                      setStatus(e.target.value);
                      setOffset(0);
                    }}
                  >
                    <option value="">All statuses</option>
                    {statuses.map((s) => (
                      <option value={s} key={s}>
                        {label(s)}
                      </option>
                    ))}
                  </select>
                  {staff && (
                    <button
                      className={
                        mine ? "filter-button chosen" : "filter-button"
                      }
                      onClick={() => {
                        setMine(!mine);
                        setOffset(0);
                      }}
                    >
                      Assigned to me
                    </button>
                  )}
                </div>
                <button
                  className="mobile-filter-toggle secondary"
                  aria-expanded={filtersOpen}
                  aria-controls="extra-ticket-filters"
                  onClick={() => setFiltersOpen(!filtersOpen)}
                >
                  {filtersOpen
                    ? "Hide filters & saved views"
                    : "More filters & saved views"}
                </button>
                <div
                  id="extra-ticket-filters"
                  className={`extra-ticket-filters ${filtersOpen ? "filters-expanded" : ""}`}
                >
                  <ViewTools
                    catalog={catalog}
                    staff={staff}
                    filters={{
                      ...filters,
                      q: search,
                      status,
                      mine,
                      kind:
                        page === "bugs"
                          ? "bug"
                          : page === "tickets"
                            ? "support"
                            : "",
                    }}
                    onFilters={(v) => {
                      setFilters(v);
                      setSearch(v.q || "");
                      setStatus(v.status || "");
                      setMine(v.mine || false);
                      setPage(
                        v.kind === "bug"
                          ? "bugs"
                          : v.kind === "support"
                            ? "tickets"
                            : "overview",
                      );
                      setOffset(0);
                    }}
                    layout={view}
                    onLayout={setView}
                  />
                </div>
                {staff && checked.length > 0 && (
                  <BulkActions
                    tickets={tickets.filter((t) => checked.includes(t.id))}
                    catalog={catalog}
                    onComplete={() => {
                      setChecked([]);
                      refresh();
                      refreshUnread();
                    }}
                  />
                )}
                {tickets.length === 0 ? (
                  <div className="empty">
                    <span className="empty-icon">
                      {page === "bugs" ? (
                        <Bug size={28} />
                      ) : (
                        <Inbox size={28} />
                      )}
                    </span>
                    <h3>
                      {search || status || mine
                        ? "No matching tickets"
                        : "A fresh start for your support."}
                    </h3>
                    <p>
                      {catalog.products.length
                        ? "Create a ticket to bring the conversation together."
                        : "Add a product and client company in Settings to get started."}
                    </p>
                    {(catalog.products.length > 0 || isAdmin) && (
                      <button
                        className="secondary"
                        onClick={() =>
                          catalog.products.length
                            ? setCreate(true)
                            : navigate("settings")
                        }
                      >
                        {catalog.products.length
                          ? "Create your first ticket"
                          : "Set up your workspace"}
                        <ArrowRight size={16} />
                      </button>
                    )}
                  </div>
                ) : view === "list" ? (
                  <div className="table-scroll">
                    <table className="ticket-list responsive-records">
                      <thead>
                        <tr>
                          {staff && (
                            <th className="selection-heading">
                              <input
                                type="checkbox"
                                aria-label="Select all visible tickets"
                                checked={
                                  tickets.length > 0 &&
                                  tickets.every((t) => checked.includes(t.id))
                                }
                                onChange={(e) =>
                                  setChecked(
                                    e.target.checked
                                      ? tickets.map((t) => t.id)
                                      : [],
                                  )
                                }
                              />
                              <span className="mobile-select-label">
                                Select all visible
                              </span>
                            </th>
                          )}
                          <th>Ticket</th>
                          <th>Client / project</th>
                          <th>Status</th>
                          <th>Severity</th>
                          <th>Assigned to</th>
                          {staff && <th>SLA</th>}
                        </tr>
                      </thead>
                      <tbody>
                        {tickets.map((t) => (
                          <tr key={t.id} onClick={() => open(t.id)}>
                            {staff && (
                              <td
                                className="selection-cell"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <input
                                  type="checkbox"
                                  aria-label={`Select ticket ${t.id}`}
                                  checked={checked.includes(t.id)}
                                  onChange={(e) =>
                                    setChecked(
                                      e.target.checked
                                        ? [...checked, t.id]
                                        : checked.filter((id) => id !== t.id),
                                    )
                                  }
                                />
                              </td>
                            )}
                            <td className="record-title">
                              <button className="ticket-title">
                                {t.title}
                              </button>
                              {staff && (
                                <div className="tag-list">
                                  {t.tags?.map((tag) => (
                                    <span className="badge" key={tag}>
                                      {tag}
                                    </span>
                                  ))}
                                </div>
                              )}
                              <small>
                                #{String(t.id).padStart(4, "0")} <span>·</span>{" "}
                                {label(t.incident_type)} <span>·</span>{" "}
                                {date(t.created_at)}
                              </small>
                            </td>
                            <td data-label="Client / project">
                              {t.company}
                              <small>{t.product}</small>
                            </td>
                            <td data-label="Status">
                              <Badge status={t.status} />
                            </td>
                            <td data-label="Severity">
                              <span className={`severity ${t.severity}`}>
                                <i />
                                {label(t.severity)}
                              </span>
                            </td>
                            <td data-label="Assigned to">
                              <span className="assignee">
                                <span className="mini-avatar">
                                  {t.assignee === "Unassigned"
                                    ? "—"
                                    : t.assignee.slice(0, 2).toUpperCase()}
                                </span>
                                {t.assignee}
                              </span>
                            </td>
                            {staff && (
                              <td data-label="SLA">
                                <SLAIndicator ticket={t} />
                              </td>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="kanban" aria-busy={busy}>
                    {statuses.map((s) => (
                      <section
                        className="kanban-column"
                        key={s}
                        onDragOver={(e) => {
                          if (staff) e.preventDefault();
                        }}
                        onDrop={(e) => {
                          e.preventDefault();
                          const t = tickets.find(
                            (t) =>
                              t.id ===
                              Number(e.dataTransfer.getData("text/plain")),
                          );
                          if (t && staff) move(t, s);
                        }}
                      >
                        <header>
                          <Badge status={s} />
                          <span>
                            {tickets.filter((t) => t.status === s).length}
                          </span>
                        </header>
                        {tickets
                          .filter((t) => t.status === s)
                          .map((t) => (
                            <button
                              key={t.id}
                              className="kanban-card"
                              draggable={staff && !busy}
                              onDragStart={(e) =>
                                e.dataTransfer.setData(
                                  "text/plain",
                                  String(t.id),
                                )
                              }
                              onClick={() => open(t.id)}
                            >
                              <small>
                                #{String(t.id).padStart(4, "0")} · {t.product}
                              </small>
                              <strong>{t.title}</strong>
                              <span>{t.company}</span>
                              <footer>
                                <span className={`severity ${t.severity}`}>
                                  <i />
                                  {t.severity.toUpperCase()}
                                </span>
                                <span className="mini-avatar">
                                  {t.assignee === "Unassigned"
                                    ? "—"
                                    : t.assignee.slice(0, 2).toUpperCase()}
                                </span>
                              </footer>
                              {staff && <SLAIndicator ticket={t} />}
                            </button>
                          ))}
                      </section>
                    ))}
                  </div>
                )}
                <div className="panel-footer">
                  <span>
                    {view === "board" && staff
                      ? "Open a card to change status or enter a resolution. With a mouse, you can also drag it between columns."
                      : "Your permissions determine which tickets appear here."}
                  </span>
                  <div>
                    <button
                      disabled={offset === 0}
                      onClick={() => setOffset(Math.max(0, offset - 100))}
                    >
                      Previous
                    </button>
                    <button
                      disabled={tickets.length < 100}
                      onClick={() => setOffset(offset + 100)}
                    >
                      Next
                    </button>
                  </div>
                </div>
              </section>
              {page === "overview" && (
                <div className="overview-note">
                  <span className="note-icon">
                    <ShieldCheck size={23} />
                  </span>
                  <div>
                    <strong>One workspace. The right visibility.</strong>
                    <p>
                      Customer conversations stay connected to your team’s work.
                      Internal notes and bugs stay private.
                    </p>
                  </div>
                  <span className="pill">PORTAL FIRST</span>
                </div>
              )}
            </>
          )}
        </div>
        <footer className="app-footer">
          RapidSupportHub{" "}
          <span>Open source support, thoughtfully connected.</span>
        </footer>
      </main>
      {create && (
        <CreateTicket
          catalog={catalog}
          user={user}
          kind={page === "bugs" ? "bug" : "support"}
          onClose={() => setCreate(false)}
          onCreated={(t) => {
            setCreate(false);
            setSelected(t);
            refresh();
          }}
        />
      )}
    </div>
  );
}

function Stat({
  title,
  value,
  icon,
  note,
}: {
  title: string;
  value: number;
  icon: React.ReactNode;
  note: string;
}) {
  return (
    <div className="stat">
      <div>
        {title}
        <span>{icon}</span>
      </div>
      <strong>{value.toString().padStart(2, "0")}</strong>
      <small>{note}</small>
    </div>
  );
}
function Badge({ status }: { status: string }) {
  return (
    <span className={`badge ${status}`}>
      <i />
      {label(status)}
    </span>
  );
}
function SLAIndicator({ ticket }: { ticket: Ticket }) {
  const active = ticket.sla?.filter((s) => !s.completed_at),
    breached = active?.some((s) => s.state === "breached"),
    risk = active?.some((s) => s.state === "at_risk");
  return (
    <span
      className={`sla-indicator ${breached ? "danger" : risk ? "warning" : ""}`}
    >
      <Clock3 size={13} />
      {breached
        ? "Breached"
        : risk
          ? "Due soon"
          : active?.some((s) => s.paused)
            ? "Paused"
            : active?.some((s) => s.target_minutes)
              ? "On track"
              : "—"}
    </span>
  );
}

function CreateTicket({
  catalog,
  user,
  kind,
  onClose,
  onCreated,
}: {
  catalog: Catalog;
  user: User;
  kind: string;
  onClose: () => void;
  onCreated: (t: Ticket) => void;
}) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const staff = isStaff(user);
  return (
    <Modal
      title={
        kind === "bug" ? "Log an internal issue" : "Create a support ticket"
      }
      onClose={onClose}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          const f = new FormData(e.currentTarget);
          try {
            onCreated(
              await api("/tickets", "POST", {
                title: f.get("title"),
                description: f.get("description"),
                kind,
                product_id: Number(f.get("product")),
                company_id: f.get("company") ? Number(f.get("company")) : null,
                severity: f.get("severity"),
                incident_type: kind === "bug" ? "bug" : f.get("type"),
                assignee_id: f.get("assignee")
                  ? Number(f.get("assignee"))
                  : null,
                reproduction: f.get("reproduction") || "",
                affected_version: f.get("version") || "",
              }),
            );
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label="Title">
          <input
            name="title"
            placeholder="A short, specific summary"
            minLength={3}
            maxLength={240}
            required
            autoFocus
          />
        </Field>
        <div className="form-grid">
          <Field label="Product / project">
            <select name="product" required defaultValue="">
              <option value="" disabled>
                Select a product
              </option>
              {catalog.products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </Field>
          {staff && kind === "support" ? (
            <Field label="Client company">
              <select name="company" required defaultValue="">
                <option value="" disabled>
                  Select a client
                </option>
                {catalog.companies.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </Field>
          ) : (
            <Field label="Affected version">
              <input
                name="version"
                disabled={!staff}
                placeholder={staff ? "e.g. 1.2.0" : "Set by your support team"}
              />
            </Field>
          )}
          <Field label="Severity">
            <select name="severity" defaultValue="sev3">
              {["sev1", "sev2", "sev3", "sev4"].map((v) => (
                <option key={v} value={v}>
                  {label(v)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Incident type">
            <select
              name="type"
              defaultValue={kind === "bug" ? "bug" : "question"}
              disabled={kind === "bug"}
            >
              {["question", "bug", "outage", "request"].map((v) => (
                <option key={v} value={v}>
                  {label(v)}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <Field label="Description">
          <textarea
            name="description"
            rows={4}
            placeholder="What happened, and what did you expect?"
            required
          />
        </Field>
        {kind === "bug" && (
          <Field label="Steps to reproduce">
            <textarea
              name="reproduction"
              rows={3}
              placeholder="1. Open…&#10;2. Click…&#10;3. Observe…"
            />
          </Field>
        )}
        {staff && (
          <Field label="Assigned to">
            <select name="assignee">
              <option value="">Unassigned</option>
              {catalog.agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </Field>
        )}
        {error && <div className="error">{error}</div>}
        <div className="modal-actions">
          <button type="button" className="secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="primary"
            disabled={busy || !catalog.products.length}
          >
            {busy
              ? "Creating…"
              : "Create " + (kind === "bug" ? "issue" : "ticket")}
            <ArrowRight size={16} />
          </button>
        </div>
      </form>
    </Modal>
  );
}

function TicketDetail({
  ticket: t,
  requestedStatus,
  user,
  catalog,
  onBack,
  onChange,
}: {
  ticket: Ticket;
  requestedStatus?: string;
  user: User;
  catalog: Catalog;
  onBack: () => void;
  onChange: (t: Ticket) => void;
}) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [internal, setInternal] = useState(false),
    [body, setBody] = useState(""),
    [resolution, setResolution] = useState(t.resolution),
    [audit, setAudit] = useState(false),
    [nextStatus, setNextStatus] = useState(requestedStatus || t.status);
  useEffect(() => {
    setNextStatus(requestedStatus || t.status);
    setResolution(t.resolution);
  }, [t.id, t.status, t.resolution, requestedStatus]);
  const staff = isStaff(user);
  async function patch(data: Record<string, unknown>) {
    setError("");
    setBusy(true);
    try {
      onChange(
        await api(`/tickets/${t.id}`, "PATCH", { version: t.version, ...data }),
      );
    } catch (e) {
      setError((e as Error).message);
      try {
        onChange(await api(`/tickets/${t.id}`));
      } catch {}
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button className="back" onClick={onBack}>
        <ArrowLeft size={16} />
        Back to workspace
      </button>
      <div className="page-heading detail-heading">
        <div>
          <div className="eyebrow">
            {t.kind === "bug" ? "INTERNAL ISSUE" : "SUPPORT TICKET"} / #
            {String(t.id).padStart(4, "0")}
          </div>
          <h1>{t.title}</h1>
          <p className="muted">
            {t.company} <span>·</span> {t.product} <span>·</span> Opened{" "}
            {date(t.created_at)} by {t.creator}
          </p>
        </div>
        <Badge status={t.status} />
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <div className="detail-layout">
        <div>
          <section className="panel description">
            <h2>Description</h2>
            <p className="prewrap">{t.description}</p>
            {t.reproduction && (
              <>
                <h3>Steps to reproduce</h3>
                <p className="prewrap">{t.reproduction}</p>
              </>
            )}
            {t.affected_version && (
              <p className="muted">Affected version: {t.affected_version}</p>
            )}
            {t.linked_bug_id && <p>Linked internal bug: #{t.linked_bug_id}</p>}
          </section>
          <section className="panel conversation">
            <div className="panel-heading">
              <h2>Conversation</h2>
              <span className="count">{t.messages?.length || 0}</span>
            </div>
            <div className="messages">
              {!t.messages?.length && (
                <p className="muted">The conversation starts here.</p>
              )}
              {t.messages?.map((m) => (
                <article
                  className={`message ${m.internal ? "private" : ""}`}
                  key={m.id}
                >
                  <header>
                    <span className="mini-avatar">
                      {m.author.slice(0, 2).toUpperCase()}
                    </span>
                    <strong>{m.author}</strong>
                    {m.internal && <span className="pill">PRIVATE NOTE</span>}
                    <time>{date(m.created_at)}</time>
                  </header>
                  <p className="prewrap">{m.body}</p>
                </article>
              ))}
            </div>
            {t.status !== "closed" && (
              <form
                className="composer"
                onSubmit={async (e) => {
                  e.preventDefault();
                  setBusy(true);
                  setError("");
                  try {
                    onChange(
                      await api(`/tickets/${t.id}/messages`, "POST", {
                        body,
                        internal,
                      }),
                    );
                    setBody("");
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                {staff && (
                  <div className="segmented">
                    <button
                      type="button"
                      className={!internal ? "selected" : ""}
                      onClick={() => setInternal(false)}
                    >
                      Public reply
                    </button>
                    <button
                      type="button"
                      className={internal ? "selected" : ""}
                      onClick={() => setInternal(true)}
                    >
                      Private note
                    </button>
                  </div>
                )}
                <textarea
                  aria-label={internal ? "Private note" : "Reply"}
                  placeholder={
                    internal
                      ? "Only your internal team can see this note."
                      : "Write a reply…"
                  }
                  rows={4}
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  required
                />
                <div className="composer-footer">
                  <small>
                    {internal
                      ? "Visible to staff only"
                      : "Visible to the customer and your team"}
                  </small>
                  <button className="primary" disabled={busy || !body.trim()}>
                    {internal ? "Add note" : "Send reply"}
                    <ArrowRight size={15} />
                  </button>
                </div>
              </form>
            )}
          </section>
          <section className="panel description">
            <h2>
              Attachments <small className="muted">10 MB per file</small>
            </h2>
            <div className="attachments">
              {t.attachments?.map((a) => (
                <a key={a.id} href={`/api/attachments/${a.id}`}>
                  {a.filename}
                  <small>
                    {(a.size / 1024).toFixed(0)} KB{" "}
                    {a.internal ? "· Private" : ""}
                  </small>
                </a>
              ))}
            </div>
            <label className="upload">
              Attach a file {staff && internal ? "(private)" : ""}
              <input
                aria-label="Attach file"
                type="file"
                disabled={busy}
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  if (!f) return;
                  const data = new FormData();
                  data.append("file", f);
                  setBusy(true);
                  setError("");
                  try {
                    await api(
                      `/tickets/${t.id}/attachments?internal=${staff && internal}`,
                      "POST",
                      data,
                    );
                    onChange(await api(`/tickets/${t.id}`));
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setBusy(false);
                    e.target.value = "";
                  }
                }}
              />
            </label>
          </section>
          {staff && (
            <section className="panel description">
              <button className="text-button" onClick={() => setAudit(!audit)}>
                Activity history {audit ? "−" : "+"}
              </button>
              {audit && (
                <div className="audit">
                  {t.audit?.map((a) => (
                    <div key={a.id}>
                      <strong>{label(a.action)}</strong>
                      <small>
                        {a.actor} · {date(a.created_at)}
                      </small>
                      {Object.keys(a.details).length > 0 && (
                        <pre>{JSON.stringify(a.details, null, 2)}</pre>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}
        </div>
        <aside className="ticket-sidebar">
          <TicketExtras
            ticket={t}
            user={user}
            catalog={catalog}
            onChange={onChange}
          />
          <section className="panel description">
            <h2>Ticket details</h2>
            {staff ? (
              <>
                <Field label="Assigned to">
                  <select
                    value={t.assignee_id || ""}
                    disabled={busy}
                    onChange={(e) =>
                      patch({
                        assignee_id: e.target.value
                          ? Number(e.target.value)
                          : null,
                      })
                    }
                  >
                    <option value="">Unassigned</option>
                    {catalog.agents.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Severity">
                  <select
                    value={t.severity}
                    disabled={busy}
                    onChange={(e) => patch({ severity: e.target.value })}
                  >
                    {["sev1", "sev2", "sev3", "sev4"].map((s) => (
                      <option key={s} value={s}>
                        {label(s)}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Incident type">
                  <select
                    value={t.incident_type}
                    disabled={busy || t.kind === "bug"}
                    onChange={(e) => patch({ incident_type: e.target.value })}
                  >
                    {["question", "bug", "outage", "request"].map((s) => (
                      <option key={s} value={s}>
                        {label(s)}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Move to status">
                  <select
                    value={nextStatus}
                    onChange={(e) => setNextStatus(e.target.value)}
                  >
                    {statuses
                      .filter(
                        (s) => t.kind !== "bug" || s !== "pending_approval",
                      )
                      .map((s) => (
                        <option key={s} value={s}>
                          {label(s)}
                        </option>
                      ))}
                  </select>
                </Field>
                <Field label="Resolution">
                  <textarea
                    rows={3}
                    placeholder="Explain the fix or solution"
                    value={resolution}
                    onChange={(e) => setResolution(e.target.value)}
                  />
                </Field>
                <button
                  className="primary full"
                  disabled={busy}
                  onClick={() => patch({ status: nextStatus, resolution })}
                >
                  Save status & resolution
                </button>
                {t.kind === "support" && (
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      const f = new FormData(e.currentTarget);
                      patch({
                        linked_bug_id: f.get("bug")
                          ? Number(f.get("bug"))
                          : null,
                      });
                    }}
                  >
                    <Field label="Linked internal bug ID">
                      <input
                        key={t.linked_bug_id}
                        type="number"
                        min="1"
                        name="bug"
                        defaultValue={t.linked_bug_id || ""}
                        placeholder="e.g. 12"
                      />
                    </Field>
                    <button className="secondary full" disabled={busy}>
                      Update bug link
                    </button>
                  </form>
                )}
              </>
            ) : (
              <>
                <p>{label(t.severity)}</p>
                <p>Assigned to {t.assignee}</p>
                {t.status === "pending_approval" && (
                  <>
                    <h3>Does this resolve your issue?</h3>
                    <p className="prewrap">{t.resolution}</p>
                    <button
                      className="primary full"
                      disabled={busy}
                      onClick={() => patch({ status: "closed" })}
                    >
                      <Check size={16} />
                      Approve & close
                    </button>
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        const f = new FormData(e.currentTarget);
                        patch({
                          status: "in_progress",
                          reason: f.get("reason"),
                        });
                      }}
                    >
                      <Field label="Still having trouble?">
                        <textarea
                          name="reason"
                          placeholder="Tell us what still needs attention"
                          required
                        />
                      </Field>
                      <button className="secondary full" disabled={busy}>
                        Reject & reopen
                      </button>
                    </form>
                  </>
                )}
              </>
            )}
          </section>
          {staff && !!t.sla?.length && (
            <section className="panel description">
              <h2>
                <Clock3 size={17} /> Service commitments
              </h2>
              <p className="muted small">
                Times follow the ticket’s SLA calendar.
              </p>
              {t.sla
                .filter(
                  (s, i, all) =>
                    (s.metric !== "update" && s.metric !== "reply") ||
                    i === all.findLastIndex((x) => x.metric === s.metric),
                )
                .map((s) => (
                  <div className="sla-card" key={s.id}>
                    <header>
                      <strong>{label(s.metric)}</strong>
                      <span className={`sla-state ${s.state}`}>
                        {label(s.state)}
                      </span>
                    </header>
                    <div>
                      {duration(s.elapsed_minutes)}{" "}
                      <span className="muted">
                        /{" "}
                        {s.target_minutes
                          ? duration(s.target_minutes)
                          : "No target"}
                      </span>
                    </div>
                    {s.target_minutes && (
                      <div className="progress">
                        <i
                          style={{
                            width: `${Math.min(100, (s.elapsed_minutes / s.target_minutes) * 100)}%`,
                            background:
                              s.state === "breached" ? "#cf4c3a" : undefined,
                          }}
                        />
                      </div>
                    )}
                    {s.due_at && <small>Due {date(s.due_at)}</small>}
                  </div>
                ))}
            </section>
          )}
        </aside>
      </div>
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
