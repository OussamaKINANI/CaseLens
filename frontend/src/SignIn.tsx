import { useState } from "react";
import type { FormEvent } from "react";

import { signIn } from "./api";
import type { ReviewerSession } from "./api";
import { Icon } from "./components/Icon";
import { getErrorMessage } from "./lib/errors";


interface SignInProps {
  notice: string | null;
  onSignedIn: (session: ReviewerSession) => void;
}

export function SignIn({ notice, onSignedIn }: SignInProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    setError(null);

    const normalizedEmail = email.trim();

    if (!normalizedEmail || !password) {
      setError("Enter your reviewer email and password.");
      return;
    }

    setSubmitting(true);

    try {
      const session = await signIn(normalizedEmail, password);
      onSignedIn(session);
    } catch (signInError) {
      setError(getErrorMessage(signInError));
      setPassword("");
      setSubmitting(false);
    }
  }

  return (
    <div className="signin-shell">
      <main className="signin-card">
        <div className="brand">
          <div className="brand-mark">
            <span>CL</span>
          </div>

          <div>
            <strong>CaseLens</strong>
            <small>Clinical review</small>
          </div>
        </div>

        <header className="signin-header">
          <p className="eyebrow">Reviewer access</p>

          <h1>Sign in to CaseLens</h1>

          <p>
            Case data, evidence, and review decisions are only available to
            an authenticated reviewer.
          </p>
        </header>

        {notice && (
          <div className="signin-notice" role="status">
            <Icon name="lock" size={14} />
            <p>{notice}</p>
          </div>
        )}

        {error && (
          <div className="intake-error" role="alert">
            <strong>Unable to sign in</strong>

            <p>{error}</p>
          </div>
        )}

        <form
          className="intake-form"
          onSubmit={(event) => {
            void handleSubmit(event);
          }}
        >
          <label>
            <span>Reviewer email</span>

            <input
              type="email"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
              }}
              autoComplete="username"
              maxLength={200}
              required
              placeholder="reviewer@caselens.local"
              disabled={submitting}
              autoFocus
            />
          </label>

          <label>
            <span>Password</span>

            <input
              type="password"
              value={password}
              onChange={(event) => {
                setPassword(event.target.value);
              }}
              autoComplete="current-password"
              maxLength={200}
              required
              disabled={submitting}
            />
          </label>

          <button
            className="btn btn-primary signin-submit"
            type="submit"
            disabled={submitting}
          >
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="signin-footnote">
          Synthetic clinical data only. CaseLens is an educational portfolio
          project and is not a medical device.
        </p>
      </main>
    </div>
  );
}
