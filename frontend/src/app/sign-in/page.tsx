import { SignIn } from "@/components/auth/sign-in";
import Link from "next/link";

export default function SignInPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <SignIn />
        <div className="text-center">
          <p className="text-sm text-gray-600">
            还没有账户？{" "}
            <Link href="/sign-up" className="font-medium text-indigo-600 hover:text-indigo-500">
              去注册
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
