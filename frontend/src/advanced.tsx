import { useEffect, useState } from "react";
import { Check, Plus } from "lucide-react";
import { api, Catalog, label, User } from "./api";
import { Field } from "./main";

type Controls = {
  entitlements: Record<string, number[]>;
  fields: any[];
  availability: Record<string, { status: string; until: string | null }>;
  automations: any[];
  releases: any[];
};
export function AdvancedSettings({
  catalog,
  users,
  refresh,
}: {
  catalog: Catalog;
  users: User[];
  refresh: () => Promise<void>;
}) {
  const [data, setData] = useState<Controls>({
      entitlements: {},
      fields: [],
      availability: {},
      automations: [],
      releases: [],
    }),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const load = () => api<Controls>("/admin/workspace-controls").then(setData);
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, []);
  async function run(fn: () => Promise<unknown>, message: string) {
    setError("");
    setNotice("");
    try {
      await fn();
      await Promise.all([load(), refresh()]);
      setNotice(message);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <>
      {error && <div className="error">{error}</div>}
      {notice && (
        <div className="success">
          <Check size={16} />
          {notice}
        </div>
      )}
      <div className="settings-grid">
        <section className="panel description">
          <h2>Client product access</h2>
          <p className="muted">
            Select the products each client company can see. Leaving every
            product unchecked preserves unrestricted access.
          </p>
          {catalog.companies.map((company) => (
            <div className="routing-group" key={company.id}>
              <strong>{company.name}</strong>
              {catalog.products.map((product) => (
                <label className="checkbox" key={product.id}>
                  <input
                    type="checkbox"
                    checked={(
                      data.entitlements[String(company.id)] || []
                    ).includes(product.id)}
                    onChange={(e) => {
                      const current =
                        data.entitlements[String(company.id)] || [];
                      run(
                        () =>
                          api(
                            `/admin/companies/${company.id}/products`,
                            "PUT",
                            {
                              product_ids: e.target.checked
                                ? [...current, product.id]
                                : current.filter((id) => id !== product.id),
                            },
                          ),
                        "Client access updated.",
                      );
                    }}
                  />
                  {product.name}
                </label>
              ))}
            </div>
          ))}
        </section>
        <section className="panel description">
          <h2>Agent availability</h2>
          <p className="muted">
            Away and out-of-office agents are skipped by automatic assignment.
          </p>
          {users
            .filter((u) =>
              u.roles.some((r) => ["admin", "agent", "developer"].includes(r)),
            )
            .map((user) => (
              <Field key={user.id} label={user.name}>
                <select
                  value={
                    data.availability[String(user.id)]?.status || "available"
                  }
                  onChange={(e) =>
                    run(
                      () =>
                        api(`/availability/${user.id}`, "PUT", {
                          status: e.target.value,
                          until: null,
                        }),
                      "Availability updated.",
                    )
                  }
                >
                  {["available", "busy", "away", "out_of_office"].map((v) => (
                    <option key={v} value={v}>
                      {label(v)}
                    </option>
                  ))}
                </select>
              </Field>
            ))}
        </section>
        <section className="panel description">
          <h2>Custom ticket fields</h2>
          <p className="muted">
            Add required or optional fields for a product and, optionally, one
            category.
          </p>
          <div className="entity-list">
            {data.fields.map((f) => (
              <div key={f.id}>
                <strong>{f.name}</strong>
                <small>
                  {catalog.products.find((p) => p.id === f.product_id)?.name} ·{" "}
                  {f.field_type}
                  {f.required ? " · required" : ""}
                </small>
              </div>
            ))}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              run(
                () =>
                  api("/admin/custom-fields", "POST", {
                    name: f.get("name"),
                    product_id: Number(f.get("product")),
                    category_id: f.get("category")
                      ? Number(f.get("category"))
                      : null,
                    kind: f.get("kind"),
                    field_type: f.get("type"),
                    required: f.get("required") === "on",
                    options: String(f.get("options") || "")
                      .split(",")
                      .map((x) => x.trim())
                      .filter(Boolean),
                    active: true,
                  }),
                "Custom field created.",
              );
              e.currentTarget.reset();
            }}
          >
            <Field label="Field name">
              <input name="name" required />
            </Field>
            <Field label="Product">
              <select name="product" required>
                <option value="">Select…</option>
                {catalog.products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Category (optional)">
              <select name="category">
                <option value="">All categories</option>
                {catalog.categories
                  .filter((c) => !c.parent_id)
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {
                        catalog.products.find((p) => p.id === c.product_id)
                          ?.name
                      }{" "}
                      · {c.name}
                    </option>
                  ))}
              </select>
            </Field>
            <div className="form-grid">
              <Field label="Field type">
                <select name="type">
                  {[
                    "text",
                    "textarea",
                    "number",
                    "date",
                    "select",
                    "checkbox",
                  ].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </Field>
              <Field label="Available for">
                <select name="kind">
                  <option value="both">Tickets and issues</option>
                  <option value="support">Support tickets</option>
                  <option value="bug">Internal issues</option>
                </select>
              </Field>
            </div>
            <Field label="Select options (comma separated)">
              <input name="options" />
            </Field>
            <label className="checkbox">
              <input type="checkbox" name="required" />
              Required
            </label>
            <button className="primary">
              <Plus size={16} />
              Add field
            </button>
          </form>
        </section>
        <section className="panel description">
          <h2>Automation and escalation</h2>
          <p className="muted">
            Apply an action when a matching ticket is created or updated.
            Conditions and actions use JSON field/value pairs.
          </p>
          <div className="entity-list">
            {data.automations.map((r) => (
              <div key={r.id}>
                <strong>{r.name}</strong>
                <small>
                  {r.trigger}
                  {r.active ? "" : " · inactive"}
                </small>
              </div>
            ))}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              try {
                const conditions = JSON.parse(
                    String(f.get("conditions") || "{}"),
                  ),
                  actions = JSON.parse(String(f.get("actions") || "{}"));
                run(
                  () =>
                    api("/admin/automations", "POST", {
                      name: f.get("name"),
                      trigger: f.get("trigger"),
                      conditions,
                      actions,
                      active: true,
                    }),
                  "Automation created.",
                );
              } catch {
                setError("Conditions and actions must be valid JSON.");
              }
            }}
          >
            <Field label="Rule name">
              <input name="name" required />
            </Field>
            <Field label="Trigger">
              <select name="trigger">
                <option value="created">Ticket created</option>
                <option value="updated">Ticket updated</option>
                <option value="sla_risk">SLA at risk</option>
                <option value="inactive">Ticket inactive</option>
              </select>
            </Field>
            <Field label="Conditions JSON">
              <input name="conditions" defaultValue='{"severity":"sev1"}' />
            </Field>
            <Field label="Actions JSON">
              <input name="actions" defaultValue='{"severity":"sev1"}' />
            </Field>
            <button className="primary">
              <Plus size={16} />
              Add automation
            </button>
          </form>
        </section>
        <section className="panel description">
          <h2>Product releases</h2>
          <p className="muted">
            Plan versions and connect resolved issues to the release containing
            their fix.
          </p>
          <div className="entity-list">
            {data.releases.map((r) => (
              <div key={r.id}>
                <strong>{r.version}</strong>
                <small>
                  {catalog.products.find((p) => p.id === r.product_id)?.name} ·{" "}
                  {label(r.status)}
                </small>
              </div>
            ))}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              run(
                () =>
                  api("/admin/releases", "POST", {
                    product_id: Number(f.get("product")),
                    version: f.get("version"),
                    status: f.get("status"),
                    notes: f.get("notes"),
                  }),
                "Release created.",
              );
              e.currentTarget.reset();
            }}
          >
            <Field label="Product">
              <select name="product" required>
                {catalog.products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Version">
              <input name="version" required placeholder="e.g. 2.4.0" />
            </Field>
            <Field label="Status">
              <select name="status">
                <option value="planned">Planned</option>
                <option value="in_progress">In progress</option>
                <option value="released">Released</option>
              </select>
            </Field>
            <Field label="Release notes">
              <textarea name="notes" />
            </Field>
            <button className="primary">
              <Plus size={16} />
              Add release
            </button>
          </form>
        </section>
      </div>
    </>
  );
}
