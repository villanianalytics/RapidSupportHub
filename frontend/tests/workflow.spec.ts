import { test, expect } from "@playwright/test";

test("administrator setup, customer conversation, Kanban and reports", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByLabel("Username", { exact: true }).fill("SupportAdmin");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.E2E_PASSWORD || "Local-e2e-password-123!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Choose your new password" }),
  ).toBeVisible();
  await page
    .getByLabel("Current password", { exact: true })
    .fill(process.env.E2E_PASSWORD || "Local-e2e-password-123!");
  await page
    .getByLabel("New password · at least 12 characters")
    .fill("Changed-local-e2e-456!");
  await page
    .getByRole("button", { name: "Save password", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your support, at a glance." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByLabel("Product / project name").fill("RapidCube");
  await page.getByRole("button", { name: "Add product", exact: true }).click();
  await expect(page.getByText("Added successfully.")).toBeVisible();
  await page.getByLabel("Company name", { exact: true }).fill("Acme Analytics");
  await page.getByRole("button", { name: "Add company", exact: true }).click();
  await expect(page.getByText("Acme Analytics", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "SLA policies", exact: true }).click();
  await page
    .getByLabel("Client company", { exact: true })
    .selectOption({ label: "Acme Analytics" });
  await page.getByRole("button", { name: "Save SLA policy" }).click();
  await expect(page.getByText("SLA policy saved.")).toBeVisible();
  await page
    .getByRole("button", { name: "Support tickets", exact: true })
    .click();
  await page.getByRole("button", { name: "New ticket", exact: true }).click();
  const modal = page.getByRole("dialog");
  await modal
    .getByLabel("Title", { exact: true })
    .fill("CSV export fails for large datasets");
  await modal
    .getByLabel("Product / project", { exact: true })
    .selectOption({ label: "RapidCube" });
  await modal
    .getByLabel("Client company", { exact: true })
    .selectOption({ label: "Acme Analytics" });
  await modal.getByLabel("Severity", { exact: true }).selectOption("sev1");
  await modal
    .getByLabel("Description", { exact: true })
    .fill("The export times out when the dataset exceeds 100,000 rows.");
  await modal
    .getByLabel("Assigned to", { exact: true })
    .selectOption({ label: "Support Administrator" });
  await modal
    .getByRole("button", { name: "Create ticket", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "CSV export fails for large datasets" }),
  ).toBeVisible();
  await page
    .getByLabel("Reply", { exact: true })
    .fill("We are investigating the timeout and will update you shortly.");
  await page.getByRole("button", { name: "Send reply" }).click();
  await expect(
    page.getByText(
      "We are investigating the timeout and will update you shortly.",
      { exact: true },
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: "Private note", exact: true }).click();
  await page
    .getByLabel("Private note", { exact: true })
    .fill("Check the export worker timeout configuration.");
  await page.getByRole("button", { name: "Add note" }).click();
  await expect(
    page.getByText("Check the export worker timeout configuration.", {
      exact: true,
    }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/ticket-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Back to workspace" }).click();
  await page.getByRole("button", { name: "Kanban view" }).click();
  await page
    .getByRole("button", { name: "Assigned to me", exact: true })
    .click();
  const card = page
    .locator(".kanban-card")
    .filter({ hasText: "CSV export fails" });
  await expect(card).toBeVisible();
  await card.dragTo(
    page
      .locator(".kanban-column")
      .filter({ has: page.locator("header .badge.in_progress") }),
  );
  await expect(
    page
      .locator(".kanban-column")
      .filter({ has: page.locator("header .badge.in_progress") })
      .getByText("CSV export fails for large datasets"),
  ).toBeVisible();
  await card.dragTo(page.locator('.kanban-column').filter({has:page.locator('header .badge.pending_approval')}));
  await expect(page.getByLabel('Move to status',{exact:true})).toHaveValue('pending_approval');
  await page.getByRole('button',{name:'Back to workspace'}).click();
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await page.getByRole("button", { name: "List view" }).click();
  await page.screenshot({
    path: "test-results/overview-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Reports", exact: true }).click();
  await page.getByRole("button", { name: "Run report", exact: true }).click();
  await expect(page.getByText("1 accessible tickets")).toBeVisible();
  await page
    .getByRole("textbox", { name: "Report name" })
    .fill("Response times by incident type");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(
    page.getByRole("button", { name: /Response times by incident type/ }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/reports-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await page.screenshot({
    path: "test-results/overview-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});

test("customer approval, private-data isolation, and shared record reports", async ({
  page,
}) => {
  const headers = {
    Origin: "http://127.0.0.1:5173",
    "X-Requested-With": "RapidSupportHub",
  };
  const login = await page.request.post("/api/auth/login", {
    data: { username: "SupportAdmin", password: "Changed-local-e2e-456!" },
  });
  expect(login.ok()).toBe(true);
  const catalog = await (await page.request.get("/api/catalog")).json();
  const org = catalog.companies[0].id;
  const user = await page.request.post("/api/admin/users", {
    headers,
    data: {
      username: "client-reviewer",
      name: "Client Reviewer",
      password: "Client-temporary-123!",
      roles: ["customer_company"],
      company_id: org,
    },
  });
  expect(user.ok()).toBe(true);
  const ticket = await (await page.request.get("/api/tickets/1")).json();
  expect(
    (
      await page.request.patch("/api/tickets/1", {
        headers,
        data: {
          version: ticket.version,
          status: "pending_approval",
          resolution: "Increased the export timeout and optimized streaming.",
        },
      })
    ).ok(),
  ).toBe(true);
  expect(
    (
      await page.request.post("/api/reports", {
        headers,
        data: {
          name: "Client ticket register",
          shared: true,
          config: {
            view: "records",
            columns: ["id", "title", "status", "resolution"],
          },
        },
      })
    ).ok(),
  ).toBe(true);
  await page.request.post("/api/auth/logout", { headers });
  await page.goto("/");
  await page.getByLabel("Username", { exact: true }).fill("client-reviewer");
  await page
    .getByLabel("Password", { exact: true })
    .fill("Client-temporary-123!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page
    .getByLabel("Current password", { exact: true })
    .fill("Client-temporary-123!");
  await page
    .getByLabel("New password · at least 12 characters")
    .fill("Client-changed-pass-456!");
  await page
    .getByRole("button", { name: "Save password", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your support, at a glance." }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Issue tracker", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Settings", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", {
      name: "CSV export fails for large datasets",
      exact: true,
    })
    .click();
  await expect(
    page.getByText("Check the export worker timeout configuration.", {
      exact: true,
    }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Private note", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Approve & close", exact: true })
    .click();
  await expect(page.locator(".detail-heading .badge")).toHaveText("Closed");
  await page.screenshot({
    path: "test-results/customer-portal.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Reports", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Build a report" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: /Client ticket register/ }).click();
  await expect(
    page.getByRole("heading", { name: "Ticket records", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("1 accessible tickets")).toBeVisible();
  await expect(
    page.getByRole("cell", {
      name: "CSV export fails for large datasets",
      exact: true,
    }),
  ).toBeVisible();
});
