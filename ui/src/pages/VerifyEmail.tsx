import { Link } from 'react-router-dom'

export default function VerifyEmail() {
  return (
    <main className="flex min-h-[calc(100vh-57px)] items-center justify-center px-4 text-center">
      <div className="max-w-sm">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-blue-100">
          <svg className="h-8 w-8 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
        </div>
        <h1 className="text-2xl font-bold text-gray-900">Check your email</h1>
        <p className="mt-3 text-gray-600">
          We've sent a verification link to your email address. Please verify your account before signing in.
        </p>
        <Link to="/login" className="mt-6 inline-block text-blue-600 hover:underline">
          Go to sign in
        </Link>
      </div>
    </main>
  )
}
