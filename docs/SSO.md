# Microsoft Entra ID single sign-on

RapidSupportHub v0.3 supports Microsoft Entra ID (formerly Azure Active Directory) using OpenID Connect authorization code flow with PKCE. A connection trusts one tenant; administrators can configure additional connections for client tenants. Users are explicitly mapped to existing portal accounts by the tenant's immutable Microsoft Object ID. There is no automatic email matching, domain trust, user creation, or role assignment.

## Register the application

1. Open Microsoft Entra admin center → Identity → Applications → App registrations → New registration.
2. Name the app **RapidSupportHub** and select **Accounts in this organizational directory only**.
3. Add a **Web** redirect URI (not SPA): `https://rapidsupporthub.com/api/auth/entra/callback`. Other installations should use the exact URI displayed in portal Settings → Single sign-on.
4. Copy **Directory (tenant) ID** and **Application (client) ID**.
5. Under Certificates & secrets, create a client secret. Copy its **Value**, not its ID. Set an expiry and arrange rotation before that date.
6. This integration requests only `openid profile`; it does not call Microsoft Graph or require Graph application permissions. Apply tenant consent requirements and, if desired, require assignment to the enterprise application. Microsoft MFA and Conditional Access follow your tenant's policies and licensing.

## Configure the portal

1. Sign in as a RapidSupportHub administrator. Keep a working local administrator login available.
2. Open **Settings → Single sign-on**. Add a connection name, tenant ID, client ID, and client secret value. Leave the connection disabled until identities are linked.
3. Create portal accounts under **People & permissions**, assigning their roles and client company normally. Their local temporary passwords remain subject to the local first-login change requirement.
4. In Entra → Users, copy each person's **Object ID**. For guests, use their guest Object ID in the configured tenant, not the object ID from their home tenant.
5. Under **Link a Microsoft user**, select the connection, portal user, and Object ID. Only active human accounts can be linked. Automation continues to use scoped API keys.
6. Edit the connection and enable it. Sign out and select **Sign in with Microsoft · connection name**. Validate the first real sign-in with a mapped account before distributing the option.

Linked users keep their current portal permissions. Microsoft sign-in satisfies authentication without requiring a change to a local temporary password. It does not change or clear that local password requirement. Local password sign-in remains available; SSO-only enforcement and automatic group/role synchronization are not implemented.

## Secrets and operation

Set `SSO_ENCRYPTION_KEY` to a Fernet key in the private server environment. Generate it once with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` in a trusted terminal, store it securely, and preserve it with backups. Do not paste it into source control. On the hosted installation it resides in the root-readable `/etc/rapidsupporthub.env`.

Client secrets are encrypted at rest using this key and are never returned by the API. A database backup alone cannot recover them without the key. Do not replace the encryption key without migrating stored secrets. Rotate an Entra client secret by editing the connection; leave the field blank to keep the existing secret. Saving an existing connection ends linked users' current Microsoft portal sessions and cancels pending sign-ins. Unlinking an identity also revokes that user's Microsoft portal sessions.

Portal sessions last 12 hours. Disabling a portal account denies subsequent requests immediately. Tenant-side changes are checked on the next Microsoft authentication; this release does not implement continuous access evaluation or Microsoft back-channel logout. Signing out ends only the portal session, not the user's Microsoft session in other applications.

Flows use a one-time, browser-bound state cookie with a 10-minute expiry, nonce validation, PKCE S256, and fixed tenant endpoints. Tokens are verified for RS256 signature, issuer, audience, lifetime, nonce, tenant, and object identity. Authorization remains entirely within the portal. Starting a second flow in the same browser replaces the first flow's cookie.

## Troubleshooting

- **AADSTS50011 / redirect mismatch:** copy the exact Web redirect URI from portal settings, including scheme and path.
- **Account not linked:** check the tenant's Object ID mapping and ensure the portal account is active and not an automation account.
- **Sign-in could not be completed:** retry from the portal; then check tenant/client IDs, secret value/expiry, app registration, and tenant policies. Provider error descriptions and tokens are deliberately not reflected to the browser.
- **Encryption key not configured:** set a valid `SSO_ENCRYPTION_KEY` in the server environment and restart the API.

References: [Microsoft authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow), [ID token claims](https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference).
