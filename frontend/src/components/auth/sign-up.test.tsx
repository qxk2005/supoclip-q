import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { SignUp } from "./sign-up";
import { signUp } from "../../lib/auth-client";

vi.mock("../../lib/auth-client", () => ({
  signUp: {
    email: vi.fn(),
  },
}));

describe("SignUp", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders API errors", async () => {
    vi.mocked(signUp.email).mockResolvedValue({
      error: { message: "Account already exists" },
    } as never);
    const user = userEvent.setup();

    render(<SignUp />);

    await user.type(screen.getByPlaceholderText("姓名"), "Jane Admin");
    await user.type(screen.getByPlaceholderText("邮箱"), "admin@example.com");
    await user.type(screen.getByPlaceholderText("密码"), "Password123!");
    await user.click(screen.getByRole("button", { name: "注册" }));

    expect(await screen.findByText("Account already exists")).toBeInTheDocument();
  });

  it("shows a success state after sign up", async () => {
    vi.mocked(signUp.email).mockResolvedValue({ error: null } as never);
    const user = userEvent.setup();

    render(<SignUp />);

    await user.type(screen.getByPlaceholderText("姓名"), "Jane Admin");
    await user.type(screen.getByPlaceholderText("邮箱"), "admin@example.com");
    await user.type(screen.getByPlaceholderText("密码"), "Password123!");
    await user.click(screen.getByRole("button", { name: "注册" }));

    expect(
      await screen.findByText("注册成功！正在为你登录…"),
    ).toBeInTheDocument();
  });
});
