import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { api, User } from "./api";
import { Field } from "./main";

export function MicrosoftSignIn() {
  const [providers, setProviders] = useState<{ id: number; name: string }[]>(
      [],
    ),
    [error, setError] = useState(() => {
      const reason = new URLSearchParams(location.search).get("sso_error");
      return reason === "access"
        ? "Your Microsoft account is not linked to an active portal user. Contact your administrator."
        : reason
          ? "Microsoft sign-in could not be completed. Please try again."
          : "";
    }),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    api("/auth/providers")
      .then(setProviders)
      .catch(() => {});
    if (location.search.includes("sso_error="))
      history.replaceState(null, "", location.pathname);
  }, []);
  return (
    <div className="sso-signin">
      {providers.length > 0 && (
        <p className="muted">Or use your organization account</p>
      )}
      {providers.map((p) => (
        <button
          key={p.id}
          type="button"
          className="secondary full"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              const result = await api(`/auth/entra/start/${p.id}`, "POST");
              location.assign(result.url);
            } catch (e) {
              setError((e as Error).message);
              setBusy(false);
            }
          }}
        >
          <ShieldCheck size={17} />
          Sign in with Microsoft · {p.name}
        </button>
      ))}
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}

type Connection = {
  id: number;
  name: string;
  tenant_id: string;
  client_id: string;
  enabled: boolean;
  has_secret: boolean;
};
export function SSOSettings({ users }: { users: User[] }) {
  const [data, setData] = useState<{
    server_ready: boolean;
    redirect_uri: string;
    connections: Connection[];
    identities: { connection_id: number; object_id: string; user_id: number }[];
  }>({
    server_ready: false,
    redirect_uri: "",
    connections: [],
    identities: [],
  });
  const [edit, setEdit] = useState<Connection | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const load = () => api("/admin/sso").then(setData);
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, []);
  async function execute(fn: () => Promise<any>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
      await load();
      setNotice("SSO settings saved.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <section className="panel description">
        <h2>Microsoft Entra ID</h2>
        <p>
          Connect Azure Active Directory for Microsoft single sign-on. Each
          connection trusts one tenant. Link approved Microsoft users to
          existing portal accounts; their roles and client access stay
          controlled here.
        </p>
        <Field label="Web redirect URI">
          <input readOnly value={data.redirect_uri} />
        </Field>
        <p className="muted">
          Register this exact URI as a <strong>Web</strong> redirect in
          Microsoft Entra → App registrations. Use a single-tenant app with
          OpenID Connect. No Microsoft Graph application permissions are needed.
        </p>
        <p className="muted">
          Local password sign-in remains available. Microsoft MFA and
          Conditional Access are enforced by your tenant. Signing out here ends
          the portal session only.
        </p>
        {!data.server_ready && (
          <div className="error">
            The server needs SSO_ENCRYPTION_KEY before connections can be saved.
          </div>
        )}
      </section>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <div className="success" role="status">
          {notice}
        </div>
      )}
      <div className="settings-grid">
        <section className="panel description">
          <h2>{edit ? "Edit connection" : "Add tenant connection"}</h2>
          <form
            key={edit?.id || "new"}
            onSubmit={(e) => {
              e.preventDefault();
              const form = e.currentTarget,
                f = new FormData(form);
              execute(async () => {
                await api(
                  edit ? `/admin/sso/${edit.id}` : "/admin/sso",
                  edit ? "PUT" : "POST",
                  {
                    name: f.get("name"),
                    tenant_id: f.get("tenant"),
                    client_id: f.get("client"),
                    client_secret: f.get("secret") || null,
                    enabled: f.get("enabled") === "on",
                  },
                );
                setEdit(null);
                form.reset();
              });
            }}
          >
            <Field label="Connection name">
              <input
                name="name"
                required
                maxLength={100}
                defaultValue={edit?.name || ""}
                placeholder="Villytics"
              />
            </Field>
            <Field label="Directory (tenant) ID">
              <input
                name="tenant"
                required
                defaultValue={edit?.tenant_id || ""}
                readOnly={!!edit}
                placeholder="00000000-0000-0000-0000-000000000000"
              />
            </Field>
            <Field label="Application (client) ID">
              <input
                name="client"
                required
                defaultValue={edit?.client_id || ""}
              />
            </Field>
            <Field
              label={
                edit
                  ? "Replacement client secret (leave blank to keep)"
                  : "Client secret value"
              }
            >
              <input
                name="secret"
                type="password"
                autoComplete="new-password"
                required={!edit}
                maxLength={4096}
              />
            </Field>
            <p className="muted small">
              Use the secret value, not its ID. It is encrypted on the server
              and never returned to the browser. Rotate it before the expiry set
              in Entra.
            </p>
            <label className="checkbox">
              <input
                name="enabled"
                type="checkbox"
                defaultChecked={edit?.enabled || false}
              />
              Enable Microsoft sign-in
            </label>
            <p className="muted small">
              Saving changes to an existing connection ends its linked users’
              Microsoft portal sessions.
            </p>
            <button className="primary" disabled={busy || !data.server_ready}>
              Save connection
            </button>
            {edit && (
              <button
                type="button"
                className="text-button"
                onClick={() => setEdit(null)}
              >
                Cancel editing
              </button>
            )}
          </form>
        </section>
        <section className="panel description">
          <h2>Tenant connections</h2>
          {!data.connections.length && (
            <p className="muted">No tenants connected yet.</p>
          )}
          {data.connections.map((c) => (
            <div className="sso-connection" key={c.id}>
              <strong>{c.name}</strong>
              <small>{c.tenant_id}</small>
              <span className="badge">
                {c.enabled ? "Enabled" : "Disabled"}
              </span>
              <button className="text-button" onClick={() => setEdit(c)}>
                Edit {c.name}
              </button>
            </div>
          ))}
          <h2>Link a Microsoft user</h2>
          <p className="muted">
            Find the user's Object ID under Entra → Users. For a guest, use the
            object ID in this connection's tenant. Email addresses are never
            used to automatically link accounts.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const form = e.currentTarget,
                f = new FormData(form);
              execute(async () => {
                await api(
                  `/admin/sso/${f.get("connection")}/identities`,
                  "POST",
                  {
                    object_id: f.get("object"),
                    user_id: Number(f.get("user")),
                  },
                );
                form.reset();
              });
            }}
          >
            <Field label="Tenant connection">
              <select name="connection" required>
                <option value="">Select a connection</option>
                {data.connections.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Portal user">
              <select name="user" required>
                <option value="">Select a user</option>
                {users
                  .filter((u) => u.active && !u.automation)
                  .map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name} ({u.username})
                    </option>
                  ))}
              </select>
            </Field>
            <Field label="Microsoft user Object ID">
              <input name="object" required />
            </Field>
            <button
              className="secondary"
              disabled={busy || !data.connections.length}
            >
              Link Microsoft user
            </button>
          </form>
        </section>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <h2>Approved Microsoft identities</h2>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Portal user</th>
                <th>Connection</th>
                <th>Object ID</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.identities.map((i) => (
                <tr key={`${i.connection_id}-${i.object_id}`}>
                  <td>
                    {users.find((u) => u.id === i.user_id)?.name || i.user_id}
                  </td>
                  <td>
                    {
                      data.connections.find((c) => c.id === i.connection_id)
                        ?.name
                    }
                  </td>
                  <td>{i.object_id}</td>
                  <td>
                    <button
                      className="text-button"
                      disabled={busy}
                      onClick={() =>
                        execute(() =>
                          api(
                            `/admin/sso/${i.connection_id}/identities/${i.object_id}`,
                            "DELETE",
                          ),
                        )
                      }
                    >
                      Unlink
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel-footer">
          Unlinking also ends the user's current Microsoft portal sessions.
          Local account access is unchanged.
        </div>
      </section>
    </>
  );
}
