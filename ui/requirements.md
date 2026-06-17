# Online Store UI — Requirements

## Functional Requirements

### Authentication
- User can register with email, password, and full name
- After registration, user sees a prompt to verify their email before logging in
- User can log in with email and password
- Authenticated session persists across page refreshes (tokens stored in localStorage)
- User can log out, clearing all stored tokens
- Expired token (401 response) redirects user to login

### Product Catalog
- Display all products returned by `GET /products`
- Filter products by category using `?category=<cat>` query param
- Search products by title (client-side filter on the fetched list)
- Each product shows: title, category, price, and image (or placeholder if no `image_url`)
- Clicking a product navigates to its detail page

### Product Detail
- Fetch and display a single product via `GET /products/{id}`
- Show: title, category, description, price, image
- User can select quantity and add to cart
- Shows loading and error states

### Shopping Cart
- Cart state is client-side only (no backend cart endpoint)
- User can add, remove, and update quantity of items
- Cart persists in localStorage
- Cart shows line items, quantities, unit prices, and total
- Checkout button navigates to checkout (requires login)

### Checkout
- Protected — redirects to login if unauthenticated
- Collects: shipping address (street, city, state, zip, country) and payment method (free-text, no real charge)
- Order summary shows cart items and total
- On submit, calls `POST /orders` with `{ customer_id, items, total_amount, shipping_address, payment_method }`
- `customer_id` is the Cognito `sub` decoded from the stored `idToken`
- On success (202), navigates to order confirmation

### Order Confirmation
- Protected — redirects to login if unauthenticated
- Displays `order_id` and status message from the `POST /orders` response
- Clears cart on arrival
- Provides link back to catalog

## Non-Functional Requirements
- Mobile responsive at 375px, 768px, and 1280px breakpoints
- API base URL configured via `VITE_API_URL` environment variable — no hardcoded URLs
- No credentials, tokens, or secrets in source code
- Accessible: semantic HTML, keyboard navigable, sufficient color contrast

## Out of Scope
- Payment processing (payment_method is a string field only)
- Order history (no backend endpoint available)
- Admin product management
- Real-time inventory updates
