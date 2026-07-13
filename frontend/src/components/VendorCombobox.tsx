import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Plus } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

interface VendorComboboxProps {
  value: string;
  onChange: (vendor: string) => void;
  /** The vendor labels the crosswalk already knows. Empty is a legitimate
   * state (a fresh install, or a failed fetch) -- the control degrades to a
   * plain text input, which is exactly what it was before this list existed. */
  known: string[];
  disabled?: boolean;
}

/**
 * The vendor field: PICK a label the crosswalk already knows, or type a new one.
 *
 * Why a combobox and not a `Select`: a vendor absent from the list must always
 * be enterable, or the first file from a new lab could never be uploaded. And
 * why not the native `<datalist>` it replaces: that dropdown cannot be styled,
 * so it arrived as an OS-shaped box in the middle of the app's own surfaces.
 *
 * The list is a PROPOSAL, never a fence. It exists because a vendor is free
 * text, and `Crestchem` and `crestchem` are two vendors to the crosswalk --
 * each then learning half of what the other did. Showing the curator what they
 * have used before is the cheapest defence against that split, and it costs
 * them nothing when the vendor really is new.
 */
export function VendorCombobox({ value, onChange, known, disabled }: VendorComboboxProps) {
  const inputId = useId();
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const trimmed = value.trim();
  // Typing filters the list; an EXACT match does not (having picked `wuxi`, the
  // curator should still see the other vendors when they reopen the list).
  const matches = useMemo(() => {
    const needle = trimmed.toLowerCase();
    if (needle === "" || known.some((k) => k.toLowerCase() === needle)) return known;
    return known.filter((k) => k.toLowerCase().includes(needle));
  }, [known, trimmed]);

  const isNew = trimmed !== "" && !known.some((k) => k.toLowerCase() === trimmed.toLowerCase());

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!wrapperRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  useEffect(() => setActive(0), [trimmed, open]);

  function pick(vendor: string) {
    onChange(vendor);
    setOpen(false);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      if (matches.length === 0) return;
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((i) => (i + step + matches.length) % matches.length);
      return;
    }
    // Enter picks the highlighted vendor -- but only while the list is open and
    // actually offering one. Otherwise it does nothing, so a curator typing a
    // brand-new vendor is never silently corrected into an existing one.
    if (event.key === "Enter" && open && matches[active] !== undefined) {
      event.preventDefault();
      pick(matches[active]);
    }
  }

  return (
    <div className="flex flex-col gap-1.5" ref={wrapperRef}>
      <Label htmlFor={inputId}>Vendor (source label)</Label>

      <div className="relative">
        <Input
          id={inputId}
          role="combobox"
          aria-expanded={open}
          aria-controls={open ? listId : undefined}
          aria-autocomplete="list"
          autoComplete="off"
          value={value}
          placeholder={known.length > 0 ? "Pick one, or type a new one" : "e.g. novascreen"}
          className="w-56 pr-8"
          disabled={disabled}
          onChange={(event) => {
            onChange(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
        {known.length > 0 ? (
          <button
            type="button"
            tabIndex={-1}
            aria-label={open ? "Hide known vendors" : "Show known vendors"}
            disabled={disabled}
            className="absolute inset-y-0 right-0 flex w-8 items-center justify-center text-muted-foreground disabled:opacity-50"
            onClick={() => setOpen((wasOpen) => !wasOpen)}
          >
            <ChevronDown
              className={cn("size-4 transition-transform duration-100", open && "rotate-180")}
            />
          </button>
        ) : null}

        {open && known.length > 0 ? (
          <ul
            id={listId}
            role="listbox"
            className="absolute top-full left-0 z-50 mt-1 max-h-56 w-56 overflow-y-auto rounded-lg bg-popover p-1 text-popover-foreground shadow-md ring-1 ring-foreground/10"
          >
            {matches.map((vendor, index) => {
              const selected = vendor.toLowerCase() === trimmed.toLowerCase();
              return (
                <li key={vendor}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={selected}
                    className={cn(
                      "relative flex w-full cursor-default items-center rounded-md py-1 pr-8 pl-1.5 text-left text-sm outline-hidden",
                      index === active && "bg-accent text-accent-foreground"
                    )}
                    // pointerdown, not click: the input's blur must not close the
                    // list out from under the pointer before the pick lands.
                    onPointerDown={(event) => {
                      event.preventDefault();
                      pick(vendor);
                    }}
                    onMouseEnter={() => setActive(index)}
                  >
                    <span className="flex-1 truncate">{vendor}</span>
                    {selected ? <Check className="absolute right-2 size-4" /> : null}
                  </button>
                </li>
              );
            })}

            {matches.length === 0 ? (
              <li className="flex items-center gap-1.5 px-1.5 py-1 text-sm text-muted-foreground">
                <Plus className="size-4 shrink-0" />
                <span className="truncate">No match — “{trimmed}” will be a new vendor.</span>
              </li>
            ) : null}
          </ul>
        ) : null}
      </div>

      <p className="text-mono-label text-muted-foreground">
        {isNew
          ? "New vendor — it will be recorded under this label."
          : known.length > 0
            ? `${known.length} known — pick one, or type a new one.`
            : " "}
      </p>
    </div>
  );
}
