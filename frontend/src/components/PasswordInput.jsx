import { useState } from 'react';

export default function PasswordInput({ id, label, ...rest }) {
  const [show, setShow] = useState(false);
  return (
    <div className="space-y-1">
      {label && (
        <label htmlFor={id} className="block text-sm font-medium text-gray-700">
          {label}
        </label>
      )}
      <div className="relative">
        <input
          id={id}
          type={show ? 'text' : 'password'}
          className="block w-full rounded-md border border-gray-300 px-3 py-2 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          {...rest}
        />
        <button
          type="button"
          onClick={() => setShow(s => !s)}
          className="absolute inset-y-0 right-0 flex items-center pr-3 text-gray-500 hover:text-gray-700"
          aria-label={show ? 'Hide password' : 'Show password'}
        >
          {show ? '🙈' : '👁'}
        </button>
      </div>
    </div>
  );
}
