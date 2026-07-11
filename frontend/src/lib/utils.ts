import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Exhaustiveness helper for discriminated unions: pass the `default` branch
 * of a `switch` on a union's discriminant here. If every case is handled,
 * TypeScript narrows the remaining value to `never` and this compiles; if a
 * future arm is added to the union without a matching `case`, this becomes a
 * compile-time type error instead of a silent runtime fall-through. */
export function assertNever(value: never): never {
  throw new Error(`Unhandled discriminant: ${JSON.stringify(value)}`)
}
