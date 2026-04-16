import fs from "fs/promises";
import path from "path";
import { MAX_PROFESSIONAL_HOTWORDS_LEN } from "@/lib/user-professional-hotwords-constants";

export { MAX_PROFESSIONAL_HOTWORDS_LEN };

export function getUserProfessionalHotwordsDir(): string {
  const fromEnv = process.env.SUPOCLIP_USER_HOTWORDS_DIR?.trim();
  if (fromEnv) {
    return path.isAbsolute(fromEnv)
      ? fromEnv
      : path.join(process.cwd(), fromEnv);
  }
  return path.join(process.cwd(), ".data", "user-professional-hotwords");
}

/** Reject path traversal and odd filenames; Better Auth ids are typically safe. */
export function safeUserIdForFilename(id: string): string | null {
  if (!/^[a-zA-Z0-9_-]{1,128}$/.test(id)) {
    return null;
  }
  return id;
}

export type UserProfessionalHotwordsPayload = {
  text: string;
  updatedAt: string;
};

export async function readUserProfessionalHotwords(
  userId: string,
): Promise<string> {
  const safe = safeUserIdForFilename(userId);
  if (!safe) {
    return "";
  }
  const filePath = path.join(
    getUserProfessionalHotwordsDir(),
    `${safe}.json`,
  );
  try {
    const raw = await fs.readFile(filePath, "utf8");
    const parsed: unknown = JSON.parse(raw);
    if (
      parsed &&
      typeof parsed === "object" &&
      "text" in parsed &&
      typeof (parsed as { text: unknown }).text === "string"
    ) {
      return (parsed as { text: string }).text.slice(
        0,
        MAX_PROFESSIONAL_HOTWORDS_LEN,
      );
    }
    return "";
  } catch (e: unknown) {
    const code = (e as NodeJS.ErrnoException).code;
    if (code === "ENOENT") {
      return "";
    }
    throw e;
  }
}

export async function writeUserProfessionalHotwords(
  userId: string,
  text: string,
): Promise<void> {
  const safe = safeUserIdForFilename(userId);
  if (!safe) {
    throw new Error("invalid user id");
  }
  const dir = getUserProfessionalHotwordsDir();
  await fs.mkdir(dir, { recursive: true });
  const filePath = path.join(dir, `${safe}.json`);
  const payload: UserProfessionalHotwordsPayload = {
    text: text.slice(0, MAX_PROFESSIONAL_HOTWORDS_LEN),
    updatedAt: new Date().toISOString(),
  };
  await fs.writeFile(filePath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
}
