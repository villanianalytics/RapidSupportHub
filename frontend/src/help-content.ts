export type Guide = {
  id: string;
  title: string;
  summary: string;
  category: string;
  audience?: "staff" | "admin" | "reporter";
  keywords?: string;
  sections: {
    title: string;
    text?: string[];
    steps?: string[];
    note?: string;
  }[];
  related?: string[];
};

export const guides: Guide[] = [
  {
    id: "email",
    title: "Connect Amazon SES for outbound email",
    category: "Administration",
    audience: "admin",
    summary:
      "Securely store SES SMTP credentials and test the connection for the outbound-email phase.",
    keywords:
      "amazon aws ses smtp email mail outbound region sandbox credentials tls starttls",
    sections: [
      {
        title: "Prepare Amazon SES",
        steps: [
          "In the Amazon SES console, select the AWS region where you will send email and verify the From identity. Verify the Reply-to identity too if you use one.",
          "Create SES SMTP credentials in that same region. SMTP credentials are different from ordinary AWS access keys.",
          "If the SES account is in the sandbox, request production access before sending to unverified recipients.",
        ],
      },
      {
        title: "Save the connection",
        steps: [
          "Open Settings and choose Email delivery, or select Configure Amazon SES from the administrator tools.",
          "Enter the AWS region, SMTP username and password, sender name, verified From address, and optional Reply-to address.",
          "Use port 587 for STARTTLS or 465 for TLS. The SES endpoint is derived from the region and cannot be replaced with an arbitrary host.",
          "Save the settings. When editing later, leave the password empty to keep the encrypted value already stored.",
        ],
      },
      {
        title: "Test safely",
        text: [
          "Select Test SMTP connection to open a secure connection and authenticate. The test does not send an email. A successful result confirms the endpoint and credentials, but SES identity, sandbox, suppression, and sending-policy problems can still affect future delivery.",
          "Every save clears the previous test result. Test again after changing a region, port, username, password, or sender setting.",
        ],
        note: "When enabled, the connection sends ticket and internal issue notifications. Creating tickets through inbound email remains a later phase.",
      },
      {
        title: "Credential protection",
        text: [
          "The SMTP password is encrypted with the server configuration key, never returned to the browser, and redacted from audit change records. Saving and testing are restricted to interactive administrators and produce audit events.",
          "Rotate SMTP credentials periodically and immediately after suspected exposure. Saving a replacement resets the connection-test status.",
        ],
      },
    ],
    related: ["api", "audit", "notifications"],
  },
  {
    id: "audit",
    title: "Investigate activity in the audit center",
    category: "Administration",
    audience: "admin",
    summary:
      "Trace requests, compare record changes, investigate failures, and export evidence.",
    keywords: "audit history security logs activity before after investigation",
    sections: [
      {
        title: "Find and investigate an event",
        steps: [
          "Open Audit center. Only interactive administrator accounts can access it.",
          "Search by actor, action, resource, request ID or IP. Use exact filters and local date/time ranges to narrow the results, then select Apply filters.",
          "Select an event to inspect its actor, authentication method, credential identifier, HTTP outcome and before-and-after changes.",
          "Select Show correlated events to see the request start, committed changes and outcome for one operation. One operation may affect several records.",
        ],
      },
      {
        title: "Export an investigation",
        steps: [
          "Apply your filters and select Export filtered CSV.",
          "The export includes all matching pages, up to 10,000 events. Narrow your filters if you exceed that limit.",
          "Protect exported files: they contain user identities, IP addresses and operational metadata.",
        ],
      },
      {
        title: "Understand the records",
        text: [
          "Requests include reads, downloads, report runs, exports, sign-ins and permission failures. Bulk updates and credential revocations also generate record changes. Background polling produces read events.",
          "A request start without a completion may indicate an interruption. A failed request may still have committed earlier changes; inspect correlated records before retrying. A successful file response does not prove the recipient received the entire file.",
          "Passwords, hashes, tokens and SSO secrets are redacted. Message, description, reproduction and resolution contents are omitted, with character counts retained. Attachment contents, raw HTTP bodies, URL query strings and OAuth codes are not captured.",
        ],
      },
      {
        title: "Retention and coverage",
        text: [
          "Records are append-only. No portal or API edit/delete operation is provided, and database triggers reject ordinary changes to audit records. Privileged database owners can bypass these protections; this is not an external immutable archive.",
          "Historical audit entries are imported once with their original timestamps and limited metadata. Previously unlogged activity cannot be reconstructed.",
          "Events are retained without automatic pruning. Operators should monitor database growth and maintain secure backups. Health checks, static files, browser-only interactions, direct database edits and operating-system activity are outside this application audit trail.",
        ],
      },
    ],
    related: ["users", "api", "sso"],
  },
  {
    id: "start",
    title: "Get started with RapidSupportHub",
    category: "Getting started",
    summary:
      "Find your workspace, understand access, and choose where to begin.",
    keywords: "overview dashboard home navigation roles permissions",
    sections: [
      {
        title: "Your workspace",
        text: [
          "Overview summarizes the tickets and issues you can access. Open a ticket title to read its conversation and current status. Use Support tickets (My support for customers) for customer requests. Staff also have an Issue tracker for internal bugs.",
        ],
      },
      {
        title: "What you can see",
        text: [
          "Customers with Own tickets access see their own support requests. Company tickets access includes support requests for their assigned company. Both permissions can be combined. Agents, developers, and administrators have workspace-wide staff access.",
          "If a menu or record is missing, contact your support administrator to check your roles. A shared report or a watcher subscription does not grant additional ticket access.",
        ],
      },
      {
        title: "Start here",
        steps: [
          "Create a support ticket for a question, enhancement, outage, or software problem.",
          "Check Notifications for replies and updates on tickets you follow.",
          "Use My account to manage your local password, or follow your organization’s Microsoft sign-in process.",
        ],
        note: "Email ticket creation and email delivery are not enabled. Use the portal for conversations.",
      },
    ],
    related: ["support-create", "find-tickets", "account", "mobile"],
  },
  {
    id: "support-create",
    title: "Create a support ticket",
    category: "Tickets & conversations",
    summary: "Give your support team the information they need to investigate.",
    keywords:
      "new incident enhancement question outage severity category product attach screenshot",
    sections: [
      {
        title: "Submit a ticket",
        steps: [
          "Open My support or Support tickets and select New ticket.",
          "Enter a specific title, choose the affected product/project and select an issue category. Staff select the client company; customer tickets use the customer’s assigned company. Assignment is determined after submission by the category rule.",
          "Choose the severity and incident type, then describe what happened and what you expected. Include any error message, steps to reproduce, and when the problem started.",
          "Select Create ticket. The ticket opens so you can add a reply or upload supporting files.",
        ],
      },
      {
        title: "Severity and incident type",
        text: [
          "Sev 1 is Critical, Sev 2 is High, Sev 3 is Normal, and Sev 4 is Low. Choose the level that reflects the impact. Categories map to Outage, Bug, Question, or Enhancement for SLA reporting. Your client’s SLA policy can define different targets for these classifications.",
        ],
      },
      {
        title: "Before submitting",
        text: [
          "Avoid including passwords, API keys, or other secrets. If the product you need is missing, ask an administrator to add it.",
        ],
        note: "A customer ticket classified as Bug is still a customer support request. Staff use the separate Issue tracker for internal engineering work.",
      },
    ],
    related: ["conversation", "approval", "find-tickets"],
  },
  {
    id: "conversation",
    title: "Reply to tickets and attach files",
    category: "Tickets & conversations",
    summary: "Keep the conversation and supporting files together.",
    keywords:
      "message comment upload attachment screenshot private note human response",
    sections: [
      {
        title: "Send a reply",
        steps: [
          "Open the ticket and go to Conversation.",
          "Write your message in the reply box, then select Send reply.",
          "Review the conversation to confirm your message was added.",
        ],
      },
      {
        title: "Add supporting files",
        steps: [
          "Find Attachments in the ticket.",
          "Choose a file from your device and upload it using the available controls.",
          "Open an attachment from the ticket to download it.",
        ],
        note: "Each attachment is limited to 10 MB. Downloads require access to the ticket. Files are downloaded rather than shown as inline previews.",
      },
      {
        title: "Public and internal activity",
        text: [
          "Public replies are visible to people who can access the support ticket. Staff can also add private notes and internal attachments; these are not visible to customers. Only a human’s public staff response satisfies the first-human-response measurement.",
        ],
      },
    ],
    related: ["approval", "notifications", "support-create"],
  },
  {
    id: "approval",
    title: "Review a proposed resolution",
    category: "Tickets & conversations",
    summary: "Approve a fix or explain why more work is needed.",
    keywords: "resolved pending approval closed reject reopen",
    sections: [
      {
        title: "Pending approval",
        text: [
          "When a staff member proposes a resolution, the support ticket moves to Pending approval. Read the resolution and try the suggested fix.",
        ],
      },
      {
        title: "Approve or reject",
        steps: [
          "Open the pending-approval ticket.",
          "If the issue is fixed, select Approve & close.",
          "If the problem remains, enter an explanation under Still having trouble? and reject the resolution. The ticket returns to In progress.",
        ],
      },
      {
        title: "What happens to timing",
        text: [
          "Resolution timing stops when staff propose the resolution. If the ticket reopens, timing resumes; the period spent awaiting approval or closed is excluded. Internal bugs are closed by staff and do not need customer approval.",
        ],
        note: "Customers can approve or reject while the ticket is Pending approval. If a ticket is already closed, ask the support team for help with reopening it.",
      },
    ],
    related: ["conversation", "notifications"],
  },
  {
    id: "find-tickets",
    title: "Find tickets and save your views",
    category: "Daily work",
    summary:
      "Use search, filters, and personal saved views to focus your queue.",
    keywords:
      "search list board filter watching assigned severity client product saved view",
    sections: [
      {
        title: "Narrow the list",
        steps: [
          "Open the ticket workspace and search by ticket title.",
          "Filter by status, severity, product, or client. Staff can select Assigned to me.",
          "Use Watching to find tickets you explicitly follow. On phones and tablets, open More filters & saved views for the additional controls.",
        ],
      },
      {
        title: "Save a personal view",
        steps: [
          "Choose your search and filters, then select List or Board.",
          "Enter a View name and select Save view.",
          "Choose it later from My saved views to restore its search, filters, and layout. Use Delete view to remove it.",
        ],
      },
      {
        title: "More results",
        text: [
          "The workspace loads up to 100 tickets per page. Use Previous and Next to see more. Saved views are personal and always respect your current ticket permissions.",
        ],
        note: "A saved view is a ticket-list shortcut. Use Reports when you need metrics, selected data columns, or CSV exports.",
      },
    ],
    related: ["notifications", "reports", "mobile"],
  },
  {
    id: "notifications",
    title: "Notifications and ticket watchers",
    category: "Daily work",
    summary:
      "Follow assignments, replies, status changes, and approval requests.",
    keywords: "inbox unread read follow subscribe updates",
    sections: [
      {
        title: "Use your inbox",
        steps: [
          "Open Notifications from the navigation menu.",
          "Select an item to mark it read and open its ticket.",
          "Use Unread only to focus the list, or Mark all as read to clear unread items.",
        ],
      },
      {
        title: "Follow a ticket",
        steps: [
          "Open a ticket you can already access.",
          "Find Follow this ticket and select Watch ticket.",
          "Select Stop watching to remove your watcher subscription. Staff can also add or remove colleagues from the watcher list.",
        ],
      },
      {
        title: "Which updates appear",
        text: [
          "The creator, current assignee, and watchers receive relevant in-app and email activity, excluding their own actions. Creators receive an email receipt for new records. Staff may receive private-note and internal issue notifications; customers do not. Access is checked again before each email is sent.",
          "The inbox refreshes about every 30 seconds. Stopping a watcher subscription does not stop notifications you receive because you are the creator or assignee.",
        ],
        note: "Notifications are in-app only. No email is sent.",
      },
    ],
    related: ["conversation", "find-tickets"],
  },
  {
    id: "mobile",
    title: "Use the portal on a phone or tablet",
    category: "Getting started",
    summary: "Navigate, create tickets, and update work using touch controls.",
    keywords: "mobile touch responsive hamburger tablet phone swipe kanban",
    sections: [
      {
        title: "Navigate and find work",
        steps: [
          "Tap the menu button at the top left to open labeled navigation.",
          "Choose a workspace. Tickets appear as cards on smaller screens.",
          "Tap More filters & saved views to show additional filters. Tap a ticket title to open its details.",
        ],
      },
      {
        title: "Update a ticket",
        text: [
          "Forms stack vertically on smaller screens. Scroll through the ticket to find Conversation, Attachments, and Ticket details. Staff can use Move to status and Save status & resolution without dragging anything.",
          "In Board view, swipe horizontally between status columns and tap a card to open it. Wide reports and administrative tables can also be swiped horizontally.",
        ],
      },
      {
        title: "Close a menu or dialog",
        text: [
          "Use the close button or tap the backdrop outside the panel. With a keyboard, Escape closes the navigation menu or help dialog.",
        ],
      },
    ],
    related: ["support-create", "conversation", "find-tickets"],
  },
  {
    id: "account",
    title: "Sign in and manage your password",
    category: "Getting started",
    summary:
      "Use a temporary password, change your password, or sign in with Microsoft.",
    keywords:
      "login reset forgot temporary account password azure entra microsoft sso",
    sections: [
      {
        title: "First local sign-in",
        steps: [
          "Use the username and temporary password supplied by your administrator.",
          "When prompted, enter the current temporary password and choose a different password of at least 12 characters.",
          "Save the password to open your workspace.",
        ],
      },
      {
        title: "Change a local password",
        steps: [
          "Open My account.",
          "Enter your current password, new password, and confirmation.",
          "Select Change password. Other sessions and API credentials for your account are revoked.",
        ],
      },
      {
        title: "Microsoft sign-in",
        text: [
          "If your organization has enabled a connection, choose Sign in with Microsoft on the login screen. Your Microsoft identity must be linked to an active portal user. The portal keeps your existing roles and client access.",
          "While signed in with Microsoft, your organization manages your Microsoft password and authentication policies. Signing out here ends the portal session only.",
        ],
        note: "For a forgotten local password, contact your administrator. Self-service email password recovery is not available.",
      },
    ],
    related: ["troubleshooting", "start"],
  },
  {
    id: "reports",
    title: "Run reports and export results",
    category: "Daily work",
    summary: "Read shared reports and understand what the numbers represent.",
    keywords:
      "reporting studio csv download average median p90 compliance records",
    sections: [
      {
        title: "Open a report",
        steps: [
          "Go to Reports.",
          "Select a saved report you can access. The report runs with your current ticket permissions.",
          "Read the grouped metrics or ticket records. For a saved report, use its CSV download control when you need an export.",
        ],
      },
      {
        title: "Understand the results",
        text: [
          "Shared reports never grant access to additional tickets. Two people may see different results from the same report because their ticket permissions differ.",
          "Duration statistics use completed measurements. Empty duration values can mean that a measurement is still incomplete. SLA durations follow the ticket’s calendar; tickets without a policy use elapsed wall-clock time.",
        ],
      },
      {
        title: "Need a different report?",
        text: [
          "An administrator or a user with Manage reports permission can build reports, choose filters and columns, and save them. Ask your administrator if you need this permission.",
        ],
      },
    ],
    related: ["find-tickets", "report-builder"],
  },
  {
    id: "agent-workflow",
    title: "Manage tickets and use the Kanban board",
    category: "Team workflows",
    audience: "staff",
    summary: "Assign work, change status, and propose customer resolutions.",
    keywords:
      "agent developer admin started in progress waiting customer resolved closed kanban drag",
    sections: [
      {
        title: "Pick up and work a ticket",
        steps: [
          "Open Support tickets. Use Assigned to me or the available filters to find work.",
          "Open a ticket and set Assigned to, Severity, or Issue category in Ticket details. Assignment requires the Ticket assigner permission or Administrator role.",
          "Choose a status under Move to status and select Save status & resolution. Add public replies to keep the customer informed; use Private note for internal discussion.",
        ],
      },
      {
        title: "Choose the right status",
        text: [
          "New is the initial queue. Started and In progress indicate active work. Waiting on customer is for information you need from the customer; a new customer reply moves a waiting ticket back to In progress.",
          "For support tickets, enter a resolution and move to Pending approval before closing. Customers can approve or reject the proposal. Internal bugs can close directly once a resolution is provided.",
        ],
      },
      {
        title: "Use the board",
        text: [
          "Choose Board in the workspace. With a mouse, drag a card to another status column. On a phone or tablet, swipe between columns and open the card to change status. Moving a support ticket to Pending approval opens its details so you can supply the resolution.",
        ],
        note: "If a ticket changed since you loaded it, refresh the record and try again. This prevents overwriting another agent’s work.",
      },
    ],
    related: ["bugs", "organization", "sla", "conversation"],
  },
  {
    id: "bugs",
    title: "Log and resolve internal bugs",
    category: "Team workflows",
    audience: "staff",
    summary:
      "Track engineering issues by product/project and connect them to support requests.",
    keywords:
      "issue tracker bug report tester reproduction affected version linked bug",
    sections: [
      {
        title: "Create a bug",
        steps: [
          "Open Issue tracker and select Log an issue.",
          "Choose the product/project, write a clear title, and describe the issue.",
          "Add reproduction steps and the affected version. Set severity and assignment as needed.",
          "Create the issue and use its conversation, private notes, and attachments to document investigation.",
        ],
      },
      {
        title: "Link customer impact",
        steps: [
          "Open the related customer support ticket.",
          "In Ticket details, enter the internal issue’s number under Linked internal bug ID.",
          "Select Update bug link. Customers do not see the linked internal record or its private details.",
        ],
      },
      {
        title: "Record the fix",
        text: [
          "Enter the resolution and set the internal bug to Closed. Internal issues do not require customer approval. Update related customer tickets separately with a customer-facing explanation and a proposed resolution.",
        ],
        note: "Admin, Agent, and Developer roles can log internal issues. Customers cannot access the Issue tracker.",
      },
    ],
    related: ["agent-workflow", "organization"],
  },
  {
    id: "organization",
    title: "Tags, duplicates, and bulk updates",
    category: "Team workflows",
    audience: "staff",
    summary: "Organize related work and update several tickets safely.",
    keywords: "tag duplicate link bulk select assignment status",
    sections: [
      {
        title: "Add tags and duplicate links",
        steps: [
          "Open a ticket and find Organization.",
          "Enter comma-separated tags. Tags are normalized to lowercase; use up to 12 tags, each up to 40 characters.",
          "If it duplicates another record, enter the original ticket ID and select Save organization. Clear that field and save to remove the link.",
        ],
        note: "Duplicate links connect records of the same kind, cannot form cycles, and preserve both records and their SLA history. Tags and duplicate links are staff-only.",
      },
      {
        title: "Update tickets in bulk",
        steps: [
          "Choose List view and select tickets using the checkboxes, or select all visible tickets.",
          "Choose a Bulk status, Bulk assignment, or both. Supply a resolution if the chosen transition needs one.",
          "Select Apply to selected. Up to 100 visible tickets can be updated at once.",
        ],
      },
      {
        title: "When a bulk update fails",
        text: [
          "Every selected ticket must pass version, access, and workflow validation. If any record fails, none are changed. Refresh the tickets and correct the selection or requested status before retrying. Mixed support/bug selections cannot all move to Pending approval because internal bugs do not use that status.",
        ],
      },
    ],
    related: ["find-tickets", "agent-workflow", "bugs"],
  },
  {
    id: "sla",
    title: "Understand SLAs and the attention queue",
    category: "Team workflows",
    audience: "staff",
    summary:
      "See what needs a response and how response and resolution clocks behave.",
    keywords:
      "sev1 sev 1 incident response time breach approaching deadline first human update calendar pause",
    sections: [
      {
        title: "Prioritize the queue",
        text: [
          "Attention needed includes active tickets with breached targets, approaching targets, unanswered customer conversations, or no assignee. Approaching means at least 80% of the target has elapsed. The queue ranks SLA urgency first, then age.",
          "Select a category or Assigned to me to narrow it. Categories overlap, so their counts are not necessarily additive. Closed and pending-approval tickets are excluded.",
        ],
      },
      {
        title: "The four measurements",
        text: [
          "First human response starts when a support ticket is created and finishes with a human public staff reply. Private notes, attachments, and automation replies do not satisfy it.",
          "Resolution starts at creation and stops at a proposed resolution. If reopened, it resumes while excluding approval/closed periods.",
          "Optional customer-reply timing starts with the first unanswered customer message. More customer messages do not reset that start. Optional progress-update timing restarts after a human public staff reply while work remains active.",
        ],
      },
      {
        title: "Calendars and history",
        text: [
          "Policies can use 24/7 or business hours with a timezone and holidays. Waiting on customer pauses clocks when the ticket’s policy enables that option.",
          "A ticket keeps the SLA policy snapshot from creation. Changing a policy does not rewrite existing tickets’ targets. Changing a ticket’s classification does not erase an in-flight breach.",
        ],
        note: "First response and resolution are measured even without a configured policy, but there is no policy target to breach. The attention queue is visual; automatic escalation is not enabled.",
      },
    ],
    related: ["agent-workflow", "reports", "sla-config"],
  },
  {
    id: "report-builder",
    title: "Build custom reports",
    category: "Daily work",
    audience: "reporter",
    summary:
      "Choose metrics or records, add filters, and save reports for reuse.",
    keywords:
      "custom reporting columns group by shared csv first response agent p90 median",
    sections: [
      {
        title: "Build and run",
        steps: [
          "Open Reports and find Build a report.",
          "Choose Grouped summary & metrics for aggregate reporting, or Ticket records & selected columns for a record list.",
          "Choose grouping and metric, or select the record columns. Add filters for the data you need.",
          "Select Run report and review the results. Name the report and select Save to keep it. Enable sharing if other users should be able to run it.",
        ],
      },
      {
        title: "Interpret time and compliance",
        text: [
          "Average, median, and P90 duration statistics use completed cycles. SLA compliance includes completed targets and open breaches; open targets that have not breached remain pending. Repeated reply/update cycles count as separate observations.",
          "Assignee grouping uses the ticket’s current assignee. First response agent uses the human who actually responded.",
        ],
      },
      {
        title: "Permissions and exports",
        text: [
          "Report creation requires an administrator role or Manage reports permission. Shared reports still run with each viewer’s current record access. Save a report before using its CSV download link.",
          "The builder supports the available ticket fields and SLA measurements. It does not execute arbitrary SQL or custom database joins.",
        ],
      },
    ],
    related: ["reports", "sla", "users"],
  },
  {
    id: "workspace",
    title: "Set up products and client companies",
    category: "Administration",
    audience: "admin",
    summary:
      "Create the workspace records used by support requests and internal issues.",
    keywords: "settings setup project product company client onboarding",
    sections: [
      {
        title: "Add workspace records",
        steps: [
          "Open Settings → Workspace.",
          "Enter the product/project name and optional description, then select Add product.",
          "Enter each client company’s name and select Add company.",
        ],
      },
      {
        title: "Connect users and service levels",
        text: [
          "Assign customer users to their client company under People & permissions. Support tickets require a company and product; internal bugs are organized by product/project.",
          "Create client-specific service targets under SLA policies. Configure those policies before creating the tickets that should use them.",
        ],
      },
      {
        title: "Staff access",
        text: [
          "Agent, Developer, and Admin roles have workspace-wide staff access. Per-project staff restrictions are not implemented. Use customer accounts for client access rather than adding customer roles to a staff account.",
        ],
      },
    ],
    related: ["users", "sla-config", "sso", "api"],
  },
  {
    id: "users",
    title: "Create users and manage access",
    category: "Administration",
    audience: "admin",
    summary: "Assign roles, reset local passwords, and disable accounts.",
    keywords:
      "admin agent developer permissions temporary password reset reports automation customer",
    sections: [
      {
        title: "Create an account",
        steps: [
          "Open Settings → People & permissions.",
          "Enter the username, display name, email, and a temporary password of at least 12 characters.",
          "Choose roles and, for customer roles, a client company. Enable Manage reports if appropriate.",
          "Create the account and share its temporary password securely. Human users must replace it at their first local login.",
        ],
      },
      {
        title: "Choose access",
        text: [
          "Admin manages workspace configuration and accounts. Agent and Developer provide staff access to support tickets and internal issues. Admin and Agent may be combined.",
          "Own tickets and Company tickets are customer roles and may be combined. Customer and staff roles cannot be combined on the same account. Automation accounts use scoped API keys rather than interactive sign-in.",
        ],
      },
      {
        title: "Change access or reset a password",
        steps: [
          "Use Edit access on the user’s row to adjust roles, report permission, company, or active status. Save access to apply the change.",
          "For another human user, open Password options. Set a different temporary password with Reset password, or keep the password and select Require password change.",
          "Use My account for your own local password.",
        ],
        note: "Access changes and local password reset actions revoke existing credentials. The next local sign-in requires a new password after a reset/forced change. Microsoft authentication is managed separately through the SSO connection and identity mapping.",
      },
    ],
    related: ["account", "sso", "api", "report-builder"],
  },
  {
    id: "sla-config",
    title: "Configure client SLA policies",
    category: "Administration",
    audience: "admin",
    summary: "Define severity-specific response and resolution commitments.",
    keywords:
      "service level sev1 sev2 calendar timezone business holiday response resolution update",
    sections: [
      {
        title: "Create or update a policy",
        steps: [
          "Open Settings → SLA policies and select a client company.",
          "Name the policy and choose a timezone and 24/7 or business-hours coverage. For business coverage, set working days, the daily time window, and holidays.",
          "Choose whether Waiting on customer pauses the clocks.",
          "Set first-response and resolution targets for each severity/incident rule. Optional reply and update targets can be left off.",
          "Select Save SLA policy. Targets are specified in minutes.",
        ],
      },
      {
        title: "Rule selection",
        text: [
          "Rules can apply to a specific incident type or all incident types for a severity. A matching specific incident rule takes precedence over that severity’s general rule. Do not create duplicate rules for the same severity and incident type.",
        ],
      },
      {
        title: "Existing tickets",
        text: [
          "Tickets snapshot the policy at creation. Saving a new policy does not retroactively change their targets or calendar. Verify the policy before opening new client tickets.",
        ],
        note: "The attention queue and reports show the resulting measurements. Email escalation and automatic SLA notifications are not configured by this screen.",
      },
    ],
    related: ["sla", "workspace", "report-builder"],
  },
  {
    id: "sso",
    title: "Configure Microsoft Entra single sign-on",
    category: "Administration",
    audience: "admin",
    summary:
      "Connect a tenant and map approved Microsoft users to portal accounts.",
    keywords:
      "azure active directory aad entra sso oidc tenant client secret object id microsoft",
    sections: [
      {
        title: "Register the application",
        steps: [
          "In Microsoft Entra App registrations, create a single-tenant application.",
          "Add a Web redirect URI using the exact value shown in Settings → Single sign-on. Do not register it as a SPA redirect.",
          "Copy the Directory (tenant) ID and Application (client) ID. Create a client secret and copy its value, not its ID.",
        ],
      },
      {
        title: "Configure and enable",
        steps: [
          "In Settings → Single sign-on, create a named connection with those IDs and the client secret. Leave it disabled while you link users.",
          "Create the portal users and assign their normal roles and client companies.",
          "Under Link a Microsoft user, select the connection and portal account, then enter the Microsoft user’s Object ID from that tenant. For guests, use the guest Object ID in the configured tenant.",
          "Edit and enable the connection. Sign out and test Sign in with Microsoft with a mapped account.",
        ],
      },
      {
        title: "Maintain the connection",
        text: [
          "Secrets are encrypted on the server and are not returned to the browser. Replace a secret before its Entra expiry; leaving the replacement field blank preserves the existing value.",
          "Saving an existing connection ends linked users’ Microsoft portal sessions. Unlinking a user also revokes that user’s Microsoft portal sessions. Local password login remains available. There is no automatic email matching, user provisioning, or group-to-role synchronization.",
        ],
        note: "If server readiness is missing, the server operator must configure SSO_ENCRYPTION_KEY. Keep that key with backups. Tenant-side account changes are checked at the next Microsoft sign-in; portal sessions last 12 hours.",
      },
    ],
    related: ["users", "account", "troubleshooting"],
  },
  {
    id: "api",
    title: "Set up REST API automation",
    category: "Administration",
    audience: "admin",
    summary:
      "Create a dedicated automation account and issue a scoped API key.",
    keywords:
      "rest api token bearer integration key scope read write reports revoke expiration",
    sections: [
      {
        title: "Create an automation identity",
        steps: [
          "Open Settings → People & permissions and create a dedicated account with Automation enabled.",
          "Choose the roles and company access needed for its work. Automation accounts do not use the interactive password login.",
          "Open Settings → API access. Select the account, name the key, choose scopes, and set an expiry.",
          "Create the key and copy it immediately into your automation’s secret store. The raw key is displayed only once.",
        ],
      },
      {
        title: "Use the key",
        text: [
          "Send the key as an Authorization: Bearer header to the REST API. Read scope permits reads, Write permits mutations, and Reports permits report endpoints. The account’s roles still restrict its data.",
          "Interactive administrator sessions are required for account/configuration and authentication-management endpoints. API keys cannot administer users or SSO. Ticket PATCH requests must include the current version; a stale version returns HTTP 409.",
        ],
      },
      {
        title: "Rotate and revoke",
        text: [
          "Use API access to revoke a key when it is no longer needed or may have been exposed. Create a replacement and update your automation before an existing key expires.",
          "Open REST API reference from the help center for endpoint schemas and examples. Never paste live API keys into ticket conversations.",
        ],
        note: "Automation replies do not satisfy first-human-response measurements. A human must propose a support-ticket resolution.",
      },
    ],
    related: ["users", "agent-workflow", "report-builder"],
  },
  {
    id: "troubleshooting",
    title: "Troubleshoot common problems",
    category: "Getting started",
    summary:
      "Resolve sign-in, missing-access, upload, and stale-record problems.",
    keywords:
      "error missing forbidden 401 403 409 stale changed failed login upload empty no results",
    sections: [
      {
        title: "I cannot sign in",
        text: [
          "Check the username supplied by your administrator; it may be your email address. A temporary local password must be changed on first login. Contact your administrator for a reset if needed.",
          "For Microsoft sign-in, verify you chose the correct organization and that your Microsoft identity is linked to an active portal account. A redirect mismatch requires the administrator to correct the Entra Web redirect URI.",
        ],
      },
      {
        title: "A ticket, menu, or report is missing",
        text: [
          "Clear search and filters, check Previous/Next, and confirm you are using the correct workspace. Ask your administrator to check your roles and company assignment. Sharing a report or following a ticket does not grant record access.",
        ],
      },
      {
        title: "My update or upload failed",
        text: [
          "“This ticket changed” means another update occurred. Reload the ticket, review the latest information, and retry your change. Copy any unsent text before refreshing.",
          "Uploads must be no larger than 10 MB and require access to the ticket. A bulk update fails as a whole if any selected ticket cannot be updated.",
          "If a new feature does not appear after a release, refresh the page to load the current app.",
        ],
      },
    ],
    related: ["account", "find-tickets", "conversation"],
  },
];
