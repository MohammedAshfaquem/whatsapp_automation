import React from "react";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  act,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { NewChatModal } from "../src/components/inbox/NewChatModal";
import { InboxPage } from "../src/pages/InboxPage";
import { SettingsPage } from "../src/pages/SettingsPage";
import { fetchApi } from "../src/api/client";
vi.mock("../src/api/client", () => ({ fetchApi: vi.fn() }));
vi.mock("../src/context/AuthContext", () => ({
  useAuth: () => ({ user: { id: 1, username: "agent", is_superuser: false } }),
}));
const api = vi.mocked(fetchApi);
const approved = {
  id: 1,
  name: "welcome",
  body_text: "Hello {{1}}, welcome {{1}}",
  status: "APPROVED",
  category: "UTILITY",
  language: "en",
};
const conversations = [
  {
    id: 1,
    customer_name: "Alice",
    customer_phone: "+14155552671",
    status: "HUMAN_HANDOVER",
    assigned_staff: "agent",
    handover_required: true,
  },
  {
    id: 2,
    customer_name: "Bob",
    customer_phone: "+14155552672",
    status: "HUMAN_HANDOVER",
    assigned_staff: "agent",
    handover_required: true,
  },
];
beforeEach(() => {
  window.history.replaceState({}, "", "/");
  window.innerWidth = 1024;
  api.mockReset();
});
function modal(templates: any[] = [approved]) {
  api.mockImplementation(async (url: any) =>
    url.includes("templates")
      ? { templates }
      : url.includes("/start/")
        ? { conversation_id: 7 }
        : ({ contacts: [] } as any),
  );
  const created = vi.fn();
  render(
    <NewChatModal isOpen onClose={() => {}} onConversationCreated={created} />,
  );
  return created;
}
async function newRecipient(phone = "+14155552671") {
  await userEvent.click(
    screen.getByRole("button", { name: "New Contact Number" }),
  );
  await userEvent.type(
    screen.getByPlaceholderText("+919876543210 or +14155552671"),
    phone,
  );
}
const submit = () =>
  userEvent.click(
    screen.getByRole("button", { name: "Send Message & Start Chat" }),
  );
const posts = () =>
  api.mock.calls.filter(([, options]) => options?.method === "POST");
// Removing the real input guard would send an invalid recipient to the backend.
test("new chat rejects malformed phone before sending", async () => {
  modal();
  await newRecipient("12345");
  await submit();
  expect(await screen.findByText(/valid E.164/)).toBeInTheDocument();
  expect(posts()).toHaveLength(0);
});
test("template requires nonempty variables before sending", async () => {
  modal();
  await newRecipient();
  await screen.findByPlaceholderText("Value for {{1}}");
  await submit();
  expect(posts()).toHaveLength(0);
  expect(
    screen.getByText(/variable.*required|variable.*empty/i),
  ).toBeInTheDocument();
});
test("repeated placeholders use one variable and preview every occurrence", async () => {
  modal();
  await newRecipient();
  await userEvent.type(
    await screen.findByPlaceholderText("Value for {{1}}"),
    "Alice",
  );
  expect(
    screen.queryByPlaceholderText("Value for {{2}}"),
  ).not.toBeInTheDocument();
  expect(screen.getByText("Hello Alice, welcome Alice")).toBeInTheDocument();
  await submit();
  await waitFor(() => expect(posts()).toHaveLength(1));
  expect(JSON.parse(posts()[0][1]!.body as string)).toMatchObject({
    phone_number: "+14155552671",
    template_variables: ["Alice"],
  });
});
test("a draft first template cannot be sent as approved", async () => {
  modal([{ ...approved, status: "DRAFT" }]);
  await newRecipient();
  await submit();
  expect(posts()).toHaveLength(0);
  expect(
    screen.getByText(/Please select.*approved template/i),
  ).toBeInTheDocument();
});
test("spaced international numbers are normalized in the request", async () => {
  modal([{ ...approved, body_text: "Welcome" }]);
  await newRecipient("+1 415 555 2671");
  await submit();
  await waitFor(() => expect(posts()).toHaveLength(1));
  expect(JSON.parse(posts()[0][1]!.body as string).phone_number).toBe(
    "+14155552671",
  );
});
function inbox(list: any[] = conversations, send?: Promise<any>) {
  api.mockImplementation(async (url: any, options: any) => {
    if (options?.method === "POST") return send || {};
    if (url.includes("/messages/")) return { messages: [] };
    if (url.includes("/api/inbox/conversations/"))
      return { conversations: list };
    return {};
  });
  render(<InboxPage />);
}
test("bot mode locks the staff composer", async () => {
  inbox([{ ...conversations[0], status: "BOT_ACTIVE", assigned_staff: null }]);
  expect(await screen.findByPlaceholderText(/Bot Mode active/)).toBeDisabled();
  expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Switch to Human" })).toBeEnabled();
});
test("another owner locks the staff composer", async () => {
  inbox([{ ...conversations[0], assigned_staff: "other" }]);
  expect(
    await screen.findByPlaceholderText(/Claimed by @other/),
  ).toBeDisabled();
  expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
});
test("switching conversations restores separate drafts", async () => {
  inbox();
  const input = await screen.findByPlaceholderText(/Type WhatsApp reply/);
  await userEvent.type(input, "Alice draft");
  await userEvent.click(screen.getByText("Bob"));
  expect(input).toHaveValue("");
  await userEvent.type(input, "Bob draft");
  await userEvent.click(screen.getAllByText("Alice")[0]);
  expect(input).toHaveValue("Alice draft");
});
test("late send response cannot erase the next conversation draft", async () => {
  let resolve!: (value: any) => void;
  const pending = new Promise((r) => {
    resolve = r;
  });
  inbox(conversations, pending);
  const input = await screen.findByPlaceholderText(/Type WhatsApp reply/);
  await userEvent.type(input, "Alice message");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  await userEvent.click(screen.getByText("Bob"));
  await userEvent.type(input, "Bob draft");
  await act(async () => resolve({}));
  expect(input).toHaveValue("Bob draft");
});
function settings(failSync = false) {
  api.mockImplementation(async (url: any) => {
    if (url.includes("/profile/")) {
      if (failSync && url.includes("sync=true"))
        throw { error: "Meta unavailable" };
      return {
        profile: {},
        meta_info: {
          is_live: true,
          quality_rating: "UNKNOWN",
          messaging_limit_tier: "UNKNOWN",
        },
        vertical_choices: [],
      };
    }
    return {};
  });
  render(<SettingsPage />);
}
async function openProfile() {
  await userEvent.click(
    await screen.findByRole("button", { name: /Business Profile/ }),
  );
}
test("unknown Meta metadata stays unknown", async () => {
  settings();
  await openProfile();
  expect(screen.getByText("● UNKNOWN")).toBeInTheDocument();
  expect(screen.getByText("UNKNOWN")).toBeInTheDocument();
  expect(screen.queryByText("● GREEN")).not.toBeInTheDocument();
});
test("failed Meta sync is visible and never claims success", async () => {
  settings(true);
  await openProfile();
  await userEvent.click(screen.getByRole("button", { name: "Sync from Meta" }));
  expect(
    await screen.findByText(/Meta unavailable|Failed to sync/),
  ).toBeInTheDocument();
  expect(
    screen.queryByText(
      "Synced official profile information from Meta Cloud API.",
    ),
  ).not.toBeInTheDocument();
});
test("freeform start cannot submit an empty message", async () => {
  modal();
  await newRecipient();
  await userEvent.click(
    screen.getByLabelText("Use Approved Template (Recommended)"),
  );
  await submit();
  expect(posts()).toHaveLength(0);
  expect(screen.getByText("Please enter a message.")).toBeInTheDocument();
});
test("ownership conflict from start is displayed without opening a conversation", async () => {
  const created = modal([{ ...approved, body_text: "Welcome" }]);
  api.mockImplementation(async (url: any) => {
    if (url.includes("/start/"))
      throw { error: "This conversation is assigned to @other." };
    return url.includes("templates") ? { templates: [] } : { contacts: [] };
  });
  await newRecipient();
  await submit();
  expect(
    await screen.findByText("This conversation is assigned to @other."),
  ).toBeInTheDocument();
  expect(created).not.toHaveBeenCalled();
});
test("initial profile load failure remains visible", async () => {
  api.mockImplementation(async (url: any) => {
    if (url.includes("/profile/")) throw { error: "Profile unavailable" };
    return {};
  });
  render(<SettingsPage />);
  await openProfile();
  expect(screen.getByText("Profile unavailable")).toBeInTheDocument();
});
test("same-name templates select and send the exact language", async () => {
  modal([
    { ...approved, body_text: "Hello" },
    { ...approved, id: 2, language: "hi", body_text: "Namaste" },
  ]);
  await newRecipient();
  await userEvent.selectOptions(
    screen.getByRole("combobox"),
    screen.getByRole("option", { name: /welcome.*\[hi\]/ }),
  );
  expect(screen.getByText("Namaste")).toBeInTheDocument();
  await submit();
  await waitFor(() => expect(posts()).toHaveLength(1));
  expect(JSON.parse(posts()[0][1]!.body as string)).toMatchObject({
    template_name: "welcome",
    template_language: "hi",
  });
});

test("typing the next reply while sending preserves the new draft", async () => {
  let resolve!: (value: any) => void;
  inbox(
    conversations,
    new Promise((r) => {
      resolve = r;
    }),
  );
  const input = await screen.findByPlaceholderText(/Type WhatsApp reply/);
  await userEvent.type(input, "Submitted message");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  await userEvent.clear(input);
  await userEvent.type(input, "Next reply");
  await act(async () => resolve({}));
  expect(input).toHaveValue("Next reply");
});

test("late transcript from the previous chat never replaces the current transcript", async () => {
  let alice!: (value: any) => void;
  api.mockImplementation(async (url: any) => {
    if (url === "/conversations/1/messages/")
      return new Promise((r) => {
        alice = r;
      });
    if (url === "/conversations/2/messages/")
      return {
        messages: [
          {
            id: 22,
            direction: "INBOUND",
            sender_type: "CUSTOMER",
            text: "Bob transcript",
            timestamp: "Now",
          },
        ],
      };
    if (url.includes("/api/inbox/conversations/")) return { conversations };
    return {};
  });
  render(<InboxPage />);
  await screen.findByPlaceholderText(/Type WhatsApp reply/);
  await userEvent.click(screen.getByText("Bob"));
  expect(await screen.findByText("Bob transcript")).toBeInTheDocument();
  await act(async () =>
    alice({
      messages: [
        {
          id: 11,
          direction: "INBOUND",
          sender_type: "CUSTOMER",
          text: "Alice transcript",
          timestamp: "Now",
        },
      ],
    }),
  );
  expect(screen.queryByText("Alice transcript")).not.toBeInTheDocument();
  expect(screen.getByText("Bob transcript")).toBeInTheDocument();
});

test('1280px inbox keeps context closed and opens it as a drawer', async () => {
  window.innerWidth = 1280;
  inbox();
  await screen.findByPlaceholderText(/Type WhatsApp reply/);
  expect(screen.queryByText('Customer Context')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', {name: 'Context'}));
  const panel = screen.getByText('Customer Context').closest('.customer-context-panel');
  expect(panel).toHaveClass('fixed', 'inset-0');
  expect(screen.getByPlaceholderText(/Type WhatsApp reply/)).toBeVisible();
});

test('1600px inbox opens context as a sidebar and converts to drawer on resize', async () => {
  window.innerWidth = 1600;
  inbox();
  const heading = await screen.findByText('Customer Context');
  expect(heading.closest('.customer-context-panel')).toHaveClass('w-80');
  expect(heading.closest('.customer-context-panel')).not.toHaveClass('fixed');
  window.innerWidth = 1280;
  fireEvent(window, new Event('resize'));
  expect(heading.closest('.customer-context-panel')).toHaveClass('fixed', 'inset-0');
});


test("saved reply inserts a draft without sending", async () => {
  api.mockImplementation(async (url:any) => {
    if(url.includes('/tools/replies/'))return {results:[{id:7,title:'Greeting snippet',body:'Hello from Neoriz'}]};
    if(url.includes('/api/inbox/conversations/'))return {conversations};
    if(url.includes('/messages/'))return {messages:[]};
    return {};
  });
  render(<InboxPage/>);
  const select=await screen.findByLabelText('Insert saved reply');
  await screen.findByPlaceholderText(/Type WhatsApp reply/);
  fireEvent.change(select,{target:{value:'7'}});
  expect(screen.getByPlaceholderText(/Type WhatsApp reply/)).toHaveValue('Hello from Neoriz');
  expect(posts()).toHaveLength(0);
});


test('inbox sync wakes immediately on focus without waiting for the polling interval', async () => {
  vi.useFakeTimers();
  Object.defineProperty(document,'hidden',{configurable:true,value:false});
  try {
    inbox();
    await act(async()=>{await Promise.resolve();});
    const before=api.mock.calls.filter(([url])=>String(url).includes('/api/inbox/conversations/')).length;
    fireEvent(window,new Event('focus'));
    await act(async()=>{await Promise.resolve();});
    expect(api.mock.calls.filter(([url])=>String(url).includes('/api/inbox/conversations/')).length).toBeGreaterThan(before);
  } finally { vi.useRealTimers(); }
});
