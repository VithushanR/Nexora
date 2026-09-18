import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  ApiClientError,
  ApiConfigurationError,
  ApiNetworkError,
  startResearch,
} from "../api/client";

function userFacingError(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (error.status === 503) {
      return "Research sign-in/setup is not configured yet. Please try again after authentication is enabled.";
    }
    if (error.status === 422) {
      return "This research topic was rejected. Please enter a clear academic research topic.";
    }
    if (error.status === 429) {
      return "Too many research requests were made. Please wait and try again later.";
    }
    if (error.status === 500) {
      return "Research could not be started. Please try again later.";
    }
    return "The research service could not complete the request. Please try again.";
  }
  if (error instanceof ApiConfigurationError) {
    return "The frontend is not configured with a backend API URL.";
  }
  if (error instanceof ApiNetworkError) {
    return "Unable to reach the research service. Check the connection and try again.";
  }
  return "Something went wrong while starting research. Please try again.";
}

export default function SearchPage() {
  const navigate = useNavigate();
  const [domain, setDomain] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmitting) {
      return;
    }

    const trimmedDomain = domain.trim();
    if (!trimmedDomain) {
      setErrorMessage("Please enter a research topic before starting.");
      return;
    }

    setErrorMessage(null);
    setIsSubmitting(true);
    try {
      const { thread_id } = await startResearch({ domain: trimmedDomain });
      navigate(`/select/${thread_id}`);
    } catch (error) {
      setErrorMessage(userFacingError(error));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-12 text-slate-900 sm:px-6">
      <section className="mx-auto w-full max-w-2xl rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200 sm:p-10">
        <p className="text-sm font-semibold uppercase tracking-wide text-blue-700">Nexora</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">
          Start a research investigation
        </h1>
        <p className="mt-4 text-base leading-7 text-slate-600">
          Enter a research topic. Nexora will find and screen academic papers, then ask you to choose the papers for the final report.
        </p>

        <form className="mt-8 space-y-5" onSubmit={handleSubmit} noValidate>
          <div>
            <label className="block text-sm font-medium text-slate-800" htmlFor="research-topic">
              Research topic
            </label>
            <textarea
              id="research-topic"
              name="domain"
              value={domain}
              onChange={(event) => setDomain(event.target.value)}
              disabled={isSubmitting}
              rows={5}
              placeholder="For example: the impact of sleep quality on university academic performance"
              className="mt-2 block w-full resize-y rounded-md border border-slate-300 px-3 py-2 text-base shadow-sm outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100 disabled:cursor-not-allowed disabled:bg-slate-100"
              aria-describedby={errorMessage ? "research-topic-error" : undefined}
            />
          </div>

          {errorMessage && (
            <p
              id="research-topic-error"
              role="alert"
              className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
            >
              {errorMessage}
            </p>
          )}

          {isSubmitting && (
            <p className="text-sm text-slate-600" role="status">
              Finding and screening papers...
            </p>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className="inline-flex w-full items-center justify-center rounded-md bg-blue-700 px-4 py-3 text-sm font-semibold text-white shadow-sm hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-slate-400 sm:w-auto"
          >
            {isSubmitting ? "Starting research..." : "Start research"}
          </button>
        </form>
      </section>
    </main>
  );
}
