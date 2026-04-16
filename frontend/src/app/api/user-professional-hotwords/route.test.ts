import { GET, PUT } from "./route";
import {
  readUserProfessionalHotwords,
  writeUserProfessionalHotwords,
} from "@/lib/user-professional-hotwords-file";
import { getServerSession } from "@/server/session";

vi.mock("@/server/session", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/user-professional-hotwords-file", () => ({
  readUserProfessionalHotwords: vi.fn(),
  writeUserProfessionalHotwords: vi.fn(),
  MAX_PROFESSIONAL_HOTWORDS_LEN: 8000,
}));

describe("/api/user-professional-hotwords", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("returns 401 when no session exists", async () => {
    vi.mocked(getServerSession).mockResolvedValue(null);

    const response = await GET();

    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toEqual({ error: "Unauthorized" });
  });

  it("returns stored text for an authenticated user", async () => {
    vi.mocked(getServerSession).mockResolvedValue({
      user: { id: "user-1" },
    } as never);
    vi.mocked(readUserProfessionalHotwords).mockResolvedValue("K8s\nGPU");

    const response = await GET();

    expect(readUserProfessionalHotwords).toHaveBeenCalledWith("user-1");
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ text: "K8s\nGPU" });
  });

  it("validates PUT payloads", async () => {
    vi.mocked(getServerSession).mockResolvedValue({
      user: { id: "user-1" },
    } as never);

    const response = await PUT(
      new Request("http://localhost/api/user-professional-hotwords", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: 123 }),
      }) as never,
    );

    expect(response.status).toBe(400);
    expect(writeUserProfessionalHotwords).not.toHaveBeenCalled();
  });

  it("writes hotwords for the signed-in user", async () => {
    vi.mocked(getServerSession).mockResolvedValue({
      user: { id: "user-1" },
    } as never);

    const response = await PUT(
      new Request("http://localhost/api/user-professional-hotwords", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: "  hello  " }),
      }) as never,
    );

    expect(writeUserProfessionalHotwords).toHaveBeenCalledWith("user-1", "  hello  ");
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      ok: true,
      text: "  hello  ",
    });
  });
});
