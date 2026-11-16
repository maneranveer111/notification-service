import { Link } from 'react-router-dom';
import Button from '../components/ui/Button';

export default function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[70vh] text-center px-4">
      <h1 className="text-7xl font-bold tracking-tight text-[#E7E5E4] font-mono mb-2">404</h1>
      <h2 className="text-lg font-semibold text-[#1C1917] mb-1">Page not found</h2>
      <p className="text-xs text-[#78716C] max-w-sm mb-6">
        The page you are looking for does not exist or has been moved to another URL.
      </p>
      <Link to="/">
        <Button>Go to Overview</Button>
      </Link>
    </div>
  );
}
