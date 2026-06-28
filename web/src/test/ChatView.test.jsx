import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock the API module so the chat view is tested in isolation.
vi.mock("../api.js", () => ({
  api: {
    createSession: vi.fn(),
    sendMessage: vi.fn(),
    getHistory: vi.fn(),
  },
}));

import { api } from "../api.js";
import ChatView from "../components/ChatView.jsx";

const persona = { id: "luna", name: "Luna", archetype: "The Cheerful Astronomer" };

describe("ChatView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    api.createSession.mockResolvedValue({ session_id: "s1", persona_id: "luna" });
  });

  it("sends a message and displays the assistant reply (Req 8.3-8.5)", async () => {
    api.sendMessage.mockResolvedValue({
      message: { id: 2, role: "assistant", content: "Hello, friend!" },
    });
    render(<ChatView persona={persona} onBack={() => {}} />);
    await waitFor(() => expect(api.createSession).toHaveBeenCalled());

    const input = screen.getByLabelText("Message");
    fireEvent.change(input, { target: { value: "hi" } });
    fireEvent.click(screen.getByText("Send"));

    expect(await screen.findByText("Hello, friend!")).toBeInTheDocument();
    // Draft cleared on success.
    await waitFor(() => expect(screen.getByLabelText("Message").value).toBe(""));
  });

  it("retains unsent text and shows an error on failure (Req 8.6)", async () => {
    api.sendMessage.mockRejectedValue(new Error("timed out"));
    render(<ChatView persona={persona} onBack={() => {}} />);
    await waitFor(() => expect(api.createSession).toHaveBeenCalled());

    const input = screen.getByLabelText("Message");
    fireEvent.change(input, { target: { value: "remember this" } });
    fireEvent.click(screen.getByText("Send"));

    expect(await screen.findByRole("alert")).toHaveTextContent("timed out");
    // Unsent text is preserved for resend.
    await waitFor(() => expect(screen.getByLabelText("Message").value).toBe("remember this"));
  });
});
