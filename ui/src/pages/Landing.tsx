import { Link } from 'react-router-dom'

export default function Landing() {
  return (
    <main className="flex min-h-[calc(100vh-57px)] flex-col items-center justify-center bg-gradient-to-br from-blue-50 to-white px-4 text-center">
      <h1 className="text-4xl font-extrabold tracking-tight text-gray-900 sm:text-5xl">
        Your store, simplified.
      </h1>
      <p className="mt-4 max-w-xl text-lg text-gray-600">
        Discover quality products across every category. Fast shipping, easy checkout.
      </p>
      <Link
        to="/products"
        className="mt-8 inline-block rounded-lg bg-blue-600 px-8 py-3 text-base font-semibold text-white shadow transition hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
      >
        Shop now
      </Link>
    </main>
  )
}
