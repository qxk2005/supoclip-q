import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { SignIn } from "./sign-in";
import { signIn } from "../../lib/auth-client";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    refresh: vi.fn(),
  }),
}));

vi.mock("../../lib/auth-client", () => ({
  signIn: {
    email: vi.fn(),
  },
}));

describe("SignIn", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows an error message when sign in fails", async () => {
    vi.mocked(signIn.email).mockResolvedValue({
      error: { message: "Invalid credentials" },
    } as never);
    const user = userEvent.setup();

    render(<SignIn />);

    await user.type(screen.getByPlaceholderText("邮箱"), "user@example.com");
    await user.type(screen.getByPlaceholderText("密码"), "Password123!");
    await user.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByText("Invalid credentials")).toBeInTheDocument();
  });

  it("shows a success state after a successful sign in", async () => {
    vi.mocked(signIn.email).mockResolvedValue({ error: null } as never);
    const user = userEvent.setup();

    render(<SignIn />);

    await user.type(screen.getByPlaceholderText("邮箱"), "user@example.com");
    await user.type(screen.getByPlaceholderText("密码"), "Password123!");
    await user.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByText("登录成功！")).toBeInTheDocument();
  });
});
