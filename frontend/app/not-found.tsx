import Link from 'next/link';
export default function NotFound() {
  return (
    <div className="empty">
      <h1>Page not found</h1>
      <p>This workspace page does not exist.</p>
      <Link href="/" className="button">
        Return to dashboard
      </Link>
    </div>
  );
}
