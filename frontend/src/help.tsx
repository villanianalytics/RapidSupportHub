import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  BookOpen,
  ChevronRight,
  ExternalLink,
  Search,
  X,
} from "lucide-react";
import { isStaff, User } from "./api";
import { guides, Guide } from "./help-content";

function available(guide: Guide, user: User) {
  if (guide.audience === "admin") return user.roles.includes("admin");
  if (guide.audience === "staff") return isStaff(user);
  if (guide.audience === "reporter")
    return user.roles.includes("admin") || user.manage_reports;
  return true;
}

export function HelpCenter({
  user,
  initialTopic = "",
  compact = false,
}: {
  user: User;
  initialTopic?: string;
  compact?: boolean;
}) {
  const [query, setQuery] = useState(""),
    [category, setCategory] = useState(""),
    [selected, setSelected] = useState(initialTopic);
  const heading = useRef<HTMLHeadingElement>(null);
  const articles = guides.filter((g) => available(g, user));
  const current = articles.find((g) => g.id === selected);
  const terms = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  const results = articles.filter(
    (g) =>
      (!category || g.category === category) &&
      terms.every((term) =>
        [
          g.title,
          g.summary,
          g.keywords,
          ...g.sections.flatMap((s) => [
            s.title,
            ...(s.text || []),
            ...(s.steps || []),
            s.note,
          ]),
        ]
          .join(" ")
          .toLowerCase()
          .includes(term),
      ),
  );
  useEffect(() => {
    if (current) heading.current?.focus();
  }, [selected]);
  function open(id: string) {
    setSelected(id);
    setQuery("");
    setCategory("");
  }
  return (
    <div className={`help-center ${compact ? "help-compact" : ""}`}>
      {!compact && (
        <div className="page-heading">
          <div>
            <div className="eyebrow">A LITTLE GUIDANCE, RIGHT HERE</div>
            <h1>Help center</h1>
            <p className="muted">
              Practical guides for your support workspace.
            </p>
          </div>
          <BookOpen size={30} />
        </div>
      )}
      <div className="help-search-controls">
        <div className="search">
          <Search size={18} />
          <input
            aria-label="Search help"
            type="search"
            placeholder="Search help: bugs, passwords, SLAs…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelected("");
            }}
          />
        </div>
        <select
          aria-label="Help category"
          value={category}
          onChange={(e) => {
            setCategory(e.target.value);
            setSelected("");
          }}
        >
          <option value="">All topics</option>
          {Array.from(new Set(articles.map((g) => g.category))).map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </div>
      {current ? (
        <article className="panel help-article">
          <button
            className="text-button"
            onClick={() => {
              setSelected("");
              setQuery("");
              setCategory("");
            }}
          >
            <ArrowLeft size={16} />
            All help topics
          </button>
          <div className="eyebrow">{current.category}</div>
          <h2 ref={heading} tabIndex={-1}>
            {current.title}
          </h2>
          <p className="help-summary">{current.summary}</p>
          {current.sections.map((s) => (
            <section key={s.title}>
              <h3>{s.title}</h3>
              {s.text?.map((t) => (
                <p key={t}>{t}</p>
              ))}
              {s.steps && (
                <ol>
                  {s.steps.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
              )}
              {s.note && <aside className="help-note">{s.note}</aside>}
            </section>
          ))}
          {current.id === "api" && (
            <a
              className="secondary"
              href="/api/docs"
              target="_blank"
              rel="noreferrer"
            >
              REST API reference
              <ExternalLink size={16} />
            </a>
          )}
          {current.related?.some((id) => articles.some((g) => g.id === id)) && (
            <section className="help-related">
              <h3>Related guides</h3>
              {current.related
                .map((id) => articles.find((g) => g.id === id))
                .filter((g): g is Guide => !!g)
                .map((g) => (
                  <button
                    className="text-button"
                    key={g.id}
                    onClick={() => open(g.id)}
                  >
                    {g.title}
                    <ChevronRight size={15} />
                  </button>
                ))}
            </section>
          )}
        </article>
      ) : (
        <>
          <div className="help-results-summary" role="status">
            {results.length} {results.length === 1 ? "guide" : "guides"}
            {query
              ? ` matching “${query}”`
              : category
                ? ` in ${category}`
                : " for your workspace"}
          </div>
          {results.length ? (
            <div className="help-grid">
              {results.map((g) => (
                <button
                  className="panel help-card"
                  key={g.id}
                  onClick={() => open(g.id)}
                >
                  <span className="eyebrow">{g.category}</span>
                  <h2>{g.title}</h2>
                  <p>{g.summary}</p>
                  <span className="help-read">
                    Read guide
                    <ChevronRight size={16} />
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <div className="panel empty">
              <Search size={26} />
              <h2>No matching help topics</h2>
              <p>
                Try a shorter search, such as “password”, “ticket”, or “report”.
              </p>
              <button
                className="secondary"
                onClick={() => {
                  setQuery("");
                  setCategory("");
                }}
              >
                Clear help filters
              </button>
            </div>
          )}
          <p className="help-footnote">
            Guides reflect the current portal. Available actions depend on your
            permissions. For account access or issues these guides do not
            resolve, contact your support administrator.
          </p>
          {user.roles.includes("admin") && (
            <a
              className="text-button"
              href="/api/docs"
              target="_blank"
              rel="noreferrer"
            >
              REST API reference
              <ExternalLink size={15} />
            </a>
          )}
        </>
      )}
    </div>
  );
}

export function HelpDialog({
  user,
  topic,
  onClose,
}: {
  user: User;
  topic: string;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const node = dialog.current,
      previous = document.body.style.overflow;
    node?.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      node?.close();
      document.body.style.overflow = previous;
    };
  }, []);
  return (
    <dialog
      ref={dialog}
      className="help-dialog"
      aria-label="Help"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <header>
        <h2>
          <BookOpen size={20} />
          Help
        </h2>
        <button
          className="icon-button"
          aria-label="Close help"
          onClick={onClose}
        >
          <X size={21} />
        </button>
      </header>
      <div className="help-dialog-body">
        <HelpCenter key={topic} user={user} initialTopic={topic} compact />
      </div>
    </dialog>
  );
}
