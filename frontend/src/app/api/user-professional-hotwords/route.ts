import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "@/server/session";
import {
  MAX_PROFESSIONAL_HOTWORDS_LEN,
  readUserProfessionalHotwords,
  writeUserProfessionalHotwords,
} from "@/lib/user-professional-hotwords-file";

/** GET /api/user-professional-hotwords — load JSON-backed hotwords for the signed-in user */
export async function GET() {
  try {
    const session = await getServerSession();

    if (!session?.user?.id) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const text = await readUserProfessionalHotwords(session.user.id);
    return NextResponse.json({ text });
  } catch (error) {
    console.error("Error reading professional hotwords:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}

/** PUT /api/user-professional-hotwords — persist { text } as JSON on the server */
export async function PUT(request: NextRequest) {
  try {
    const session = await getServerSession();

    if (!session?.user?.id) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body: unknown = await request.json();
    if (
      !body ||
      typeof body !== "object" ||
      !("text" in body) ||
      typeof (body as { text: unknown }).text !== "string"
    ) {
      return NextResponse.json(
        { error: "Invalid body: expected { text: string }" },
        { status: 400 },
      );
    }

    const text = (body as { text: string }).text.slice(
      0,
      MAX_PROFESSIONAL_HOTWORDS_LEN,
    );

    await writeUserProfessionalHotwords(session.user.id, text);

    return NextResponse.json({ ok: true, text });
  } catch (error) {
    console.error("Error saving professional hotwords:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
