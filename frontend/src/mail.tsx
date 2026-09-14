import { useEffect, useState } from "react";
import { Check, Mail, Send } from "lucide-react";
import { api, date } from "./api";
import { Field } from "./main";

type Configuration = {
  region: string;
  endpoint: string;
  port: number;
  username: string;
  from_email: string;
  from_name: string;
  reply_to: string;
  enabled: boolean;
  has_password: boolean;
  last_tested_at: string | null;
  last_test_ok: boolean | null;
  updated_at: string;
};

export function EmailSettings() {
  const [data, setData] = useState<{
    server_ready: boolean;
    configuration: Configuration | null;
  }>({ server_ready: false, configuration: null });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const load = () => api("/admin/email").then(setData);
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, []);
  async function execute(action: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      await load();
      setNotice(success);
    } catch (e) {
      setError((e as Error).message);
      await load().catch(() => {});
    } finally {
      setBusy(false);
    }
  }
  const config = data.configuration;
  return (
    <>
      <section className="panel description">
        <div className="email-heading">
          <div>
            <div className="eyebrow">NEXT-PHASE READINESS</div>
            <h2>Amazon SES SMTP</h2>
          </div>
          <Mail size={25} />
        </div>
        <p>
          Store the credentials RapidSupportHub will use for outbound email.
          Saving or testing this configuration does not send a message and does
          not enable ticket creation by email.
        </p>
        <p className="muted">
          Create SMTP credentials in the Amazon SES console for the selected
          region. They are different from AWS access keys. Verify the From and
          Reply-to identities in SES and request production access before
          sending to addresses outside the SES sandbox.
        </p>
        {!data.server_ready && (
          <div className="error">
            The server encryption key must be configured before SMTP credentials
            can be saved.
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
          <Check size={16} /> {notice}
        </div>
      )}
      <div className="settings-grid">
        <section className="panel description">
          <h2>{config ? "Update SMTP configuration" : "Configure SMTP"}</h2>
          <form
            key={config?.updated_at || "new"}
            onSubmit={(event) => {
              event.preventDefault();
              const form = event.currentTarget;
              const values = new FormData(form);
              execute(
                () =>
                  api("/admin/email", "PUT", {
                    region: values.get("region"),
                    port: Number(values.get("port")),
                    username: values.get("username"),
                    password: values.get("password") || null,
                    from_email: values.get("from_email"),
                    from_name: values.get("from_name"),
                    reply_to: values.get("reply_to"),
                    enabled: values.get("enabled") === "on",
                  }),
                "Amazon SES SMTP settings saved. Run the connection test after every credential change.",
              );
            }}
          >
            <div className="form-grid">
              <Field label="AWS region">
                <input
                  name="region"
                  list="ses-regions"
                  defaultValue={config?.region || "us-east-1"}
                  placeholder="us-east-1"
                  required
                />
              </Field>
              <datalist id="ses-regions">
                {["us-east-1", "us-east-2", "us-west-1", "us-west-2"].map(
                  (region) => (
                    <option key={region} value={region} />
                  ),
                )}
              </datalist>
              <Field label="SMTP port">
                <select name="port" defaultValue={String(config?.port || 587)}>
                  <option value="587">587 · STARTTLS</option>
                  <option value="465">465 · TLS wrapper</option>
                </select>
              </Field>
            </div>
            <Field label="SES SMTP username">
              <input
                name="username"
                defaultValue={config?.username || ""}
                autoComplete="off"
                required
              />
            </Field>
            <Field
              label={
                config
                  ? "Replacement SMTP password (leave blank to keep)"
                  : "SES SMTP password"
              }
            >
              <input
                name="password"
                type="password"
                autoComplete="new-password"
                required={!config}
                maxLength={4096}
              />
            </Field>
            <div className="form-grid">
              <Field label="From email address">
                <input
                  name="from_email"
                  type="email"
                  defaultValue={config?.from_email || ""}
                  required
                />
              </Field>
              <Field label="From display name">
                <input
                  name="from_name"
                  defaultValue={config?.from_name || "RapidSupportHub"}
                  required
                />
              </Field>
            </div>
            <Field label="Reply-to email address (optional)">
              <input
                name="reply_to"
                type="email"
                defaultValue={config?.reply_to || ""}
              />
            </Field>
            <label className="checkbox">
              <input
                name="enabled"
                type="checkbox"
                defaultChecked={config?.enabled || false}
              />
              Mark this connection ready for outbound email
            </label>
            <p className="muted small">
              This readiness switch is reserved for the outbound-email phase;
              the current release will not send ticket email.
            </p>
            <button className="primary" disabled={busy || !data.server_ready}>
              Save SMTP configuration
            </button>
          </form>
        </section>
        <section className="panel description">
          <h2>Connection status</h2>
          {!config ? (
            <p className="muted">Save the configuration to test it.</p>
          ) : (
            <>
              <dl className="configuration-summary">
                <div>
                  <dt>Endpoint</dt>
                  <dd>{config.endpoint}</dd>
                </div>
                <div>
                  <dt>Security</dt>
                  <dd>
                    {config.port === 587 ? "STARTTLS · 587" : "TLS · 465"}
                  </dd>
                </div>
                <div>
                  <dt>Credential</dt>
                  <dd>
                    {config.has_password ? "Stored encrypted" : "Missing"}
                  </dd>
                </div>
                <div>
                  <dt>Readiness</dt>
                  <dd>{config.enabled ? "Enabled" : "Disabled"}</dd>
                </div>
              </dl>
              <div
                className={config.last_test_ok ? "success" : "email-test-state"}
              >
                {config.last_tested_at
                  ? `${config.last_test_ok ? "Connection successful" : "Connection failed"} · ${date(config.last_tested_at)}`
                  : "Connection has not been tested since it was saved."}
              </div>
              <button
                className="secondary"
                disabled={busy}
                onClick={() =>
                  execute(
                    () => api("/admin/email/test", "POST"),
                    "Connected and authenticated successfully. No email was sent.",
                  )
                }
              >
                <Send size={16} />
                Test SMTP connection
              </button>
            </>
          )}
          <p className="muted small email-security-note">
            The password is never returned to the browser or included in audit
            records. Connection tests authenticate only; they do not send mail.
          </p>
        </section>
      </div>
    </>
  );
}
