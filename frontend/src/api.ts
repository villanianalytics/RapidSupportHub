export type User = {
  auth_method?: "local" | "entra";
  id: number;
  username: string;
  name: string;
  email: string;
  phone: string;
  roles: string[];
  company_id: number | null;
  manage_reports: boolean;
  must_change_password: boolean;
  active: boolean;
  automation: boolean;
};
export type Catalog = {
  products: { id: number; name: string; description: string }[];
  companies: { id: number; name: string }[];
  agents: { id: number; name: string }[];
  categories: {
    id: number;
    name: string;
    display_name: string;
    kind: string;
    incident_type: string;
    parent_id: number | null;
    product_id: number;
  }[];
  issue_types: { id: number; name: string; classification: string }[];
  custom_fields: {
    id: number;
    name: string;
    product_id: number;
    category_id: number | null;
    kind: string;
    field_type: string;
    required: boolean;
    options: string[];
  }[];
  releases: {
    id: number;
    product_id: number;
    version: string;
    status: string;
  }[];
};
export type SLACycle = {
  id: number;
  metric: string;
  target_minutes: number | null;
  elapsed_minutes: number;
  state: string;
  completed_at: string | null;
  due_at: string | null;
  paused: boolean;
};
export type Ticket = {
  watching?: boolean;
  watchers?: { id: number; name: string }[];
  tags?: string[];
  duplicate_of_id?: number | null;
  attention?: string[];
  id: number;
  title: string;
  description: string;
  kind: string;
  incident_type: string;
  category_id: number | null;
  subcategory_id: number | null;
  issue_type_id: number | null;
  category: string;
  subcategory: string;
  issue_type: string;
  severity: string;
  status: string;
  company_id: number | null;
  product_id: number;
  creator_id: number;
  assignee_id: number | null;
  resolution: string;
  created_at: string;
  updated_at: string;
  version: number;
  creator: string;
  submitter?: { id: number; name: string; email: string; phone: string };
  assignee: string;
  product: string;
  company: string;
  reproduction?: string;
  affected_version?: string;
  linked_bug_id?: number | null;
  fixed_release_id?: number | null;
  fixed_release?: string;
  custom_values?: Record<string, unknown>;
  relations?: { ticket_id: number; relation: string; title: string }[];
  sla?: SLACycle[];
  messages?: {
    id: number;
    author: string;
    body: string;
    internal: boolean;
    created_at: string;
  }[];
  attachments?: {
    id: number;
    filename: string;
    size: number;
    internal: boolean;
  }[];
  audit?: {
    id: number;
    actor: string;
    action: string;
    details: Record<string, unknown>;
    created_at: string;
  }[];
};
let sessionGeneration = 0;
export class SessionChangedError extends Error {}
export async function api<T = any>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const generation = sessionGeneration;
  const form = body instanceof FormData;
  const response = await fetch("/api" + path, {
    method,
    credentials: "include",
    headers: {
      "X-Requested-With": "RapidSupportHub",
      ...(!form && body !== undefined
        ? { "Content-Type": "application/json" }
        : {}),
    },
    body: body === undefined ? undefined : form ? body : JSON.stringify(body),
  });
  if (!response.ok) {
    if (generation !== sessionGeneration)
      throw new SessionChangedError("Session changed");
    if (response.status === 401 && path !== "/auth/login")
      window.dispatchEvent(new Event("rsh:session-ended"));
    let data;
    try {
      data = await response.json();
    } catch {
      throw Error(`Request failed (${response.status})`);
    }
    throw Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  }
  const data = await response.json();
  if (generation !== sessionGeneration)
    throw new SessionChangedError("Session changed");
  if (["/auth/login", "/auth/logout", "/auth/password"].includes(path))
    sessionGeneration++;
  return data;
}
export const statuses = [
  "new",
  "started",
  "in_progress",
  "waiting_customer",
  "pending_approval",
  "closed",
];
export const label = (s: string) =>
  ({
    new: "New",
    started: "Started",
    in_progress: "In progress",
    waiting_customer: "Waiting on customer",
    pending_approval: "Resolved · pending customer approval",
    closed: "Closed",
    sev1: "Sev 1 · Critical",
    sev2: "Sev 2 · High",
    sev3: "Sev 3 · Normal",
    sev4: "Sev 4 · Low",
    customer_own: "Own tickets",
    customer_company: "Company tickets",
    assigner: "Ticket assigner",
    request: "Enhancement",
    enhancement: "Enhancement",
    first_response: "First human response",
    reply: "Customer reply",
    update: "Progress update",
    resolution: "Resolution",
  })[s] || s.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
export const isStaff = (u: User) =>
  u.roles.some((r) => ["admin", "agent", "developer"].includes(r));
export const date = (s: string) =>
  new Date(s.endsWith("Z") ? s : s + "Z").toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
export const duration = (n: number | null) =>
  n === null ? "—" : n < 60 ? `${Math.round(n)}m` : `${(n / 60).toFixed(1)}h`;
