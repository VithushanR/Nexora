import { useAuth } from "../auth/AuthContext";
import GoogleSignInButton from "../auth/GoogleSignInButton";

export default function LoginPage() {
  const { scriptReady, signInError } = useAuth();

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-gradient-to-br from-violet-950 via-purple-900 to-violet-900">
      {/* Decorative background */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-24 -top-24 h-[500px] w-[500px] rounded-full bg-violet-600/15 blur-[100px]" />
        <div className="absolute -bottom-32 -right-32 h-[600px] w-[600px] rounded-full bg-purple-500/15 blur-[100px]" />
        <div className="absolute bottom-0 left-1/2 h-72 w-[160%] -translate-x-1/2 rounded-t-[50%] bg-gradient-to-t from-violet-500/10 to-transparent" />
        <div className="absolute left-1/2 top-1/2 h-[300px] w-[300px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-violet-400/5 blur-[80px]" />
      </div>

      <div className="relative z-10 mx-auto flex w-full max-w-5xl items-center gap-20 px-6 py-12">
        {/* Left — branding */}
        <div className="hidden flex-1 lg:block">
          <img
            src="/nexora-logo.png"
            alt="Nexora"
            className="mb-8 h-16 w-16 rounded-2xl shadow-lg shadow-violet-500/20"
          />
          <p className="text-sm font-medium uppercase tracking-[0.25em] text-violet-300/80">
            Nexora
          </p>
          <h1 className="mt-2 text-[52px] font-bold leading-[1.1] tracking-tight text-white">
            EXPLORE
            <br />
            RESEARCH
          </h1>
          <p className="mt-5 text-lg font-medium leading-relaxed text-violet-200">
            Where Your Research Ideas
            <br />
            Become Discovery
          </p>
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-violet-300/70">
            Embark on a research journey where every corner of
            the academic world is within your reach
          </p>
        </div>

        {/* Right — login card */}
        <div className="w-full max-w-[420px] mx-auto lg:mx-0">
          <div className="rounded-3xl border border-white/[0.12] bg-white/[0.08] p-8 shadow-2xl shadow-black/20 backdrop-blur-2xl sm:p-10">
            {/* Mobile logo */}
            <div className="mb-8 flex items-center gap-3 lg:hidden">
              <img
                src="/nexora-logo.png"
                alt="Nexora"
                className="h-11 w-11 rounded-xl"
              />
              <span className="text-xl font-bold text-white">Nexora</span>
            </div>

            <h2 className="text-2xl font-bold text-white">Welcome back</h2>
            <p className="mt-2 text-sm text-violet-200/80">
              Sign in to access your research workspace
            </p>

            {/* Error */}
            {signInError && (
              <div className="mt-5 rounded-xl bg-red-500/15 border border-red-400/20 px-4 py-3 text-sm text-red-200">
                {signInError}
              </div>
            )}

            {/* Google sign-in */}
            <div className="mt-8">
              <div className="flex items-center justify-center overflow-hidden">
                <GoogleSignInButton width={300} />
              </div>

              {!scriptReady && (
                <p className="mt-3 text-center text-xs text-violet-300/50">
                  Initializing Google Sign-In…
                </p>
              )}
            </div>

            {/* Divider */}
            <div className="my-8 flex items-center gap-3">
              <div className="h-px flex-1 bg-white/10" />
              <span className="text-xs text-violet-300/50">Powered by Nexora Research</span>
              <div className="h-px flex-1 bg-white/10" />
            </div>

            <p className="text-center text-xs leading-relaxed text-violet-300/40">
              By signing in, you agree to Nexora's terms of service
              and privacy policy
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
