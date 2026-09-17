"use client";

import { Search } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { StatusGlyph } from "@/components/ui/StatusPill";
import { useDismiss } from "@/components/ui/useDismiss";
import { useIncidents } from "@/lib/api/queries";
import { useWorkspace } from "@/state/workspace";

import styles from "./shell.module.css";

export function GlobalSearch() {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const incidents = useIncidents();
  const router = useRouter();
  const pathname = usePathname();
  const close = useCallback(() => setOpen(false), []);
  useDismiss(wrapperRef, open, close);

  const results = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("ru");
    if (!needle) return [];
    return (incidents.data?.items ?? [])
      .filter((item) =>
        [item.id, item.district, item.region, item.nearest_settlement?.name ?? ""].some((value) =>
          value.toLocaleLowerCase("ru").includes(needle),
        ),
      )
      .slice(0, 7);
  }, [incidents.data, query]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (event.key === "/" && !["INPUT", "TEXTAREA"].includes(target.tagName)) {
        event.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const choose = (id: string) => {
    setQuery("");
    setOpen(false);
    inputRef.current?.blur();
    if (pathname === "/") {
      useWorkspace.getState().selectIncident(id);
    } else {
      router.push(`/?incident=${encodeURIComponent(id)}`);
    }
  };

  return (
    <div ref={wrapperRef} className={styles.search}>
      <Search size={14} strokeWidth={1.75} className={styles.searchIcon} />
      <input
        ref={inputRef}
        className={styles.searchInput}
        type="search"
        placeholder="Поиск: KR-042, район, посёлок"
        aria-label="Поиск событий"
        role="combobox"
        aria-expanded={open && query.length > 0}
        aria-controls="global-search-results"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setActive(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setActive((value) => Math.min(value + 1, results.length - 1));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActive((value) => Math.max(value - 1, 0));
          } else if (event.key === "Enter" && results[active]) {
            choose(results[active].id);
          } else if (event.key === "Escape") {
            setOpen(false);
            inputRef.current?.blur();
          }
        }}
      />
      {!query && <span className={styles.searchKbd}>/</span>}
      {open && query.trim() && (
        <div className={styles.menu} id="global-search-results" role="listbox" style={{ width: 320 }}>
          {results.length === 0 && <div className={styles.menuHint}>Ничего не найдено</div>}
          {results.map((item, index) => (
            <button
              key={item.id}
              type="button"
              role="option"
              aria-selected={index === active}
              data-active={index === active}
              className={styles.menuItem}
              onMouseEnter={() => setActive(index)}
              onClick={() => choose(item.id)}
            >
              <StatusGlyph status={item.status} />
              <span className="mono">{item.id}</span>
              <span>{item.district}</span>
              <span className={styles.menuMeta}>P {item.priority}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
