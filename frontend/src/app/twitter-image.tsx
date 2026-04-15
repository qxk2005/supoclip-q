import { createSocialImageResponse } from "@/lib/social-image";

export const runtime = "edge";

export const alt = "SupoClip — 将长视频剪成爆款短片";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function Image() {
  return createSocialImageResponse();
}
