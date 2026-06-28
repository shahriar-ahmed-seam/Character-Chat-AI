import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import CharacterPicker from "../components/CharacterPicker.jsx";

describe("CharacterPicker", () => {
  const personas = [
    { id: "elias", name: "Elias", archetype: "The Cynical Detective" },
    { id: "luna", name: "Luna", archetype: "The Cheerful Astronomer" },
  ];

  it("renders selectable personas (Req 8.1)", () => {
    render(<CharacterPicker personas={personas} onSelect={() => {}} />);
    expect(screen.getByText("Elias")).toBeInTheDocument();
    expect(screen.getByText("The Cheerful Astronomer")).toBeInTheDocument();
  });

  it("shows the empty state when no personas exist (Req 8.2)", () => {
    render(<CharacterPicker personas={[]} onSelect={() => {}} />);
    expect(screen.getByText(/no characters are available/i)).toBeInTheDocument();
  });

  it("shows an error with retry (Req 8.6)", () => {
    const onRetry = vi.fn();
    render(<CharacterPicker personas={[]} error="boom" onRetry={onRetry} onSelect={() => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent("boom");
    fireEvent.click(screen.getByText("Retry"));
    expect(onRetry).toHaveBeenCalled();
  });

  it("invokes onSelect when a persona is clicked", () => {
    const onSelect = vi.fn();
    render(<CharacterPicker personas={personas} onSelect={onSelect} />);
    fireEvent.click(screen.getByText("Elias"));
    expect(onSelect).toHaveBeenCalledWith(personas[0]);
  });
});
