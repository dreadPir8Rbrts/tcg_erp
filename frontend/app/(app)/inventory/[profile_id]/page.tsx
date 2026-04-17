"use client";

/**
 * Unified inventory page — /inventory
 *
 * Add inventory via:
 *   - Manual search (default) — search by card name or card number
 *   - Quick Scan (Google Vision OCR) — camera icon → select image → OCR match
 *   - Claude Vision — camera icon → select image → AI identification
 *
 * Flow: search/scan → card preview → confirm form → add to inventory
 * Available to both vendors and collectors.
 */

import { useState, useEffect, useRef, useMemo } from "react";
import {
  searchCards,
  searchCardsSmart,
  identifyCard,
  quickIdentifyCard,
  addInventoryItem,
  getInventory,
  getCardPricing,
  getSoldComps,
  type Card,
  type InventoryItemWithCard,
  type SoldCompsParams,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Loader2 } from "lucide-react";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const UNGRADED_CONDITIONS = [
  { value: "nm", label: "NM" },
  { value: "lp", label: "LP" },
  { value: "mp", label: "MP" },
  { value: "hp", label: "HP" },
  { value: "dmg", label: "DMG" },
];

const GRADING_COMPANIES = [
  { value: "psa", label: "PSA" },
  { value: "bgs", label: "BGS" },
  { value: "cgc", label: "CGC" },
  { value: "other", label: "Other" },
];

const PSA_GRADES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => ({
  value: String(n),
  label: String(n),
}));

const BGS_GRADES = [
  "1.5", "2", "2.5", "3", "3.5", "4", "4.5", "5",
  "5.5", "6", "6.5", "7", "7.5", "8", "8.5", "9", "9.5",
  "10 (Gold label)", "10 (Black label)",
].map((v) => ({ value: v, label: v.replace(" (Gold label)", " Gold").replace(" (Black label)", " Black") }));

const CGC_GRADES = [
  "1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5", "5",
  "5.5", "6", "6.5", "7", "7.5", "8", "8.5", "9", "9.5",
  "10 (GM)", "10 (Pristine)", "10 (Perfect)",
].map((v) => ({ value: v, label: v }));

function gradeOptionsForCompany(company: string) {
  if (company === "psa") return PSA_GRADES;
  if (company === "bgs") return BGS_GRADES;
  if (company === "cgc") return CGC_GRADES;
  return [];
}

/** Human-readable condition label for the inventory list. */
function formatCondition(item: InventoryItemWithCard): string {
  if (item.condition_type === "ungraded") {
    return (item.condition_ungraded ?? "—").toUpperCase();
  }
  const company =
    item.grading_company === "other"
      ? (item.grading_company_other ?? "Other")
      : (item.grading_company ?? "—").toUpperCase();
  return `${company} ${item.grade ?? ""}`.trim();
}

type ScanMode = "quick" | "claude";

interface ConfirmState {
  card: Card;
  confidence?: number;
  method?: string;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function CardRow({ card, onSelect }: { card: Card; onSelect: (c: Card) => void }) {
  return (
    <button
      onClick={() => onSelect(card)}
      className="w-full flex items-center gap-3 border rounded-lg px-3 py-2 hover:bg-muted/50 transition-colors text-left"
    >
      {card.image_url ? (
        <div className="w-10 aspect-[3/4] flex-shrink-0 rounded overflow-hidden border">
          <img src={card.image_url} alt={card.name} className="w-full h-full object-contain" />
        </div>
      ) : (
        <div className="w-10 aspect-[3/4] flex-shrink-0 rounded border bg-muted" />
      )}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{card.name}</p>
        <p className="text-xs text-muted-foreground">{card.set_name} · #{card.card_num}</p>
        {card.rarity && <p className="text-xs text-muted-foreground">{card.rarity}</p>}
      </div>
    </button>
  );
}

function InventoryRow({ item }: { item: InventoryItemWithCard }) {
  return (
    <div className="flex items-center gap-3 border rounded-lg px-3 py-2">
      {item.image_url ? (
        <div className="w-10 aspect-[3/4] flex-shrink-0 rounded overflow-hidden border">
          <img src={item.image_url} alt={item.card_name} className="w-full h-full object-contain" />
        </div>
      ) : (
        <div className="w-10 aspect-[3/4] flex-shrink-0 rounded border bg-muted" />
      )}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{item.card_name}</p>
        <p className="text-xs text-muted-foreground">{item.set_name} · #{item.card_num}</p>
        <div className="flex items-center gap-2 mt-1">
          <Badge variant="secondary" className="text-xs">{formatCondition(item)}</Badge>
          {item.rarity && <span className="text-xs text-muted-foreground">{item.rarity}</span>}
        </div>
      </div>
      <div className="text-right flex-shrink-0">
        {item.asking_price != null && (
          <p className="text-sm font-medium">${Number(item.asking_price).toFixed(2)}</p>
        )}
        <div className="flex gap-1 mt-1 justify-end">
          {item.is_for_sale && <span className="text-xs text-muted-foreground">Sale</span>}
          {item.is_for_trade && <span className="text-xs text-muted-foreground">Trade</span>}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function InventoryPage() {
  // Inventory
  const [inventory, setInventory] = useState<InventoryItemWithCard[]>([]);
  const [loadingInventory, setLoadingInventory] = useState(true);
  const [inventorySearch, setInventorySearch] = useState("");

  // Search
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Card[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  // Advanced search
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [advName, setAdvName] = useState("");
  const [advNum, setAdvNum] = useState("");
  const [advSet, setAdvSet] = useState("");
  const [advLang, setAdvLang] = useState("");

  // Scan
  const [scanMenuOpen, setScanMenuOpen] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const quickScanInputRef = useRef<HTMLInputElement>(null);
  const claudeScanInputRef = useRef<HTMLInputElement>(null);
  const scanMenuRef = useRef<HTMLDivElement>(null);

  // Confirm form
  const [confirm, setConfirm] = useState<ConfirmState | null>(null);
  const [conditionType, setConditionType] = useState<"ungraded" | "graded">("ungraded");
  const [conditionUngraded, setConditionUngraded] = useState("nm");
  const [gradingCompany, setGradingCompany] = useState("psa");
  const [grade, setGrade] = useState("");
  const [gradingCompanyOther, setGradingCompanyOther] = useState("");
  const [askingPrice, setAskingPrice] = useState("");
  const [isForSale, setIsForSale] = useState(true);
  const [isForTrade, setIsForTrade] = useState(false);
  const [quantity, setQuantity] = useState("1");
  const [notes, setNotes] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // Pricing debug
  const [pricingResult, setPricingResult] = useState<unknown>(null);
  const [pricingLoading, setPricingLoading] = useState(false);
  const [pricingError, setPricingError] = useState<string | null>(null);
  const pricingPrefetchRef = useRef<Promise<unknown> | null>(null);

  // Sold comps debug
  const [compsConditionType, setCompsConditionType] = useState<"ungraded" | "graded">("ungraded");
  const [compsConditionUngraded, setCompsConditionUngraded] = useState("nm");
  const [compsGradingCompany, setCompsGradingCompany] = useState("psa");
  const [compsGrade, setCompsGrade] = useState("");
  const [compsResult, setCompsResult] = useState<unknown>(null);
  const [compsLoading, setCompsLoading] = useState(false);
  const [compsError, setCompsError] = useState<string | null>(null);

  useEffect(() => {
    getInventory()
      .then(setInventory)
      .catch(() => {})
      .finally(() => setLoadingInventory(false));
  }, []);

  // Close scan menu on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (scanMenuRef.current && !scanMenuRef.current.contains(e.target as Node)) {
        setScanMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // Tokenizer for smart search: extracts card_num and language_code, passes remainder as q
  function parseSearchQuery(raw: string): { q?: string; card_num?: string; language_code?: string } {
    const LANG_ALIASES: Record<string, string> = {
      en: "en", english: "en",
      ja: "ja", japanese: "ja",
    };
    const tokens = raw.trim().split(/\s+/);
    let card_num: string | undefined;
    let language_code: string | undefined;
    const remaining: string[] = [];
    for (const token of tokens) {
      const langKey = token.toLowerCase();
      if (/^\d+(?:\/\d+)?$/.test(token) && !card_num) {
        card_num = token;
      } else if (langKey in LANG_ALIASES && !language_code) {
        language_code = LANG_ALIASES[langKey];
      } else {
        remaining.push(token);
      }
    }
    return {
      ...(remaining.length > 0 ? { q: remaining.join(" ") } : {}),
      ...(card_num ? { card_num } : {}),
      ...(language_code ? { language_code } : {}),
    };
  }

  // Debounced smart search
  useEffect(() => {
    if (!query.trim()) { setSearchResults(null); return; }
    const timer = setTimeout(async () => {
      setSearching(true);
      setSearchError(null);
      try {
        const params = parseSearchQuery(query);
        const results = await searchCardsSmart(params);
        setSearchResults(results);
      } catch {
        setSearchError("Search failed. Please try again.");
      } finally {
        setSearching(false);
      }
    }, 350);
    return () => clearTimeout(timer);
  }, [query]);

  function selectCard(card: Card, confidence?: number, method?: string) {
    setConfirm({ card, confidence, method });
    setQuery("");
    setSearchResults(null);
    setScanError(null);
    setConditionType("ungraded");
    setConditionUngraded("nm");
    setGradingCompany("psa");
    setGrade("");
    setGradingCompanyOther("");
    setAskingPrice("");
    setIsForSale(true);
    setIsForTrade(false);
    setQuantity("1");
    setNotes("");
    setAddError(null);
    // Reset pricing debug state for the new card
    pricingPrefetchRef.current = null;
    setPricingResult(null);
    setPricingError(null);
    setCompsResult(null);
    setCompsError(null);
    setCompsConditionType("ungraded");
    setCompsConditionUngraded("nm");
    setCompsGradingCompany("psa");
    setCompsGrade("");
    prefetchPricing(card.id);
  }

  async function handleAdvancedSearch() {
    if (!advName && !advNum && !advSet) return;
    setSearching(true);
    setSearchError(null);
    try {
      const results = await searchCards({
        ...(advName ? { name: advName } : {}),
        ...(advNum ? { card_num: advNum } : {}),
        ...(advSet ? { set_name: advSet } : {}),
        ...(advLang ? { language_code: advLang } : {}),
      });
      setSearchResults(results);
    } catch {
      setSearchError("Search failed. Please try again.");
    } finally {
      setSearching(false);
    }
  }

  async function handleScan(file: File, mode: ScanMode) {
    setScanMenuOpen(false);
    setScanning(true);
    setScanError(null);
    try {
      if (mode === "quick") {
        const result = await quickIdentifyCard(file);
        if (!result.matched || !result.card_id) {
          setScanError(
            result.reason === "no_text_detected"
              ? "No card text detected. Try better lighting or use Claude Vision."
              : "Couldn't match this card. Try Claude Vision for better accuracy."
          );
          return;
        }
        selectCard(
          {
            id: result.card_id,
            name: result.name!,
            card_num: result.card_num!,
            category: result.category!,
            rarity: result.rarity,
            image_url: result.image_url,
            set_name: result.set_name!,
            series_name: result.series_name!,
          },
          result.confidence,
          result.method
        );
      } else {
        const result = await identifyCard(file);
        selectCard(
          {
            id: result.card_id,
            name: result.name,
            card_num: result.card_num,
            category: result.category,
            rarity: result.rarity,
            image_url: result.image_url,
            set_name: result.set_name,
            series_name: result.series_name,
          },
          result.confidence
        );
      }
    } catch (err: unknown) {
      setScanError(err instanceof Error ? err.message : "Scan failed. Please try again.");
    } finally {
      setScanning(false);
    }
  }

  function prefetchPricing(cardId: string) {
    pricingPrefetchRef.current = (async () => {
      let result = await getCardPricing(cardId);
      while ((result as { http_status: number }).http_status === 202) {
        await new Promise((resolve) => setTimeout(resolve, 3000));
        result = await getCardPricing(cardId);
      }
      return result;
    })();
  }

  async function handleFetchPricing() {
    if (!confirm) return;
    setPricingLoading(true);
    setPricingError(null);
    setPricingResult(null);
    try {
      const result = pricingPrefetchRef.current
        ? await pricingPrefetchRef.current
        : await (async () => {
            let r = await getCardPricing(confirm.card.id);
            while ((r as { http_status: number }).http_status === 202) {
              await new Promise((resolve) => setTimeout(resolve, 3000));
              r = await getCardPricing(confirm.card.id);
            }
            return r;
          })();
      setPricingResult(result);
    } catch (e) {
      setPricingError(e instanceof Error ? e.message : "Failed to fetch pricing");
    } finally {
      setPricingLoading(false);
    }
  }

  async function handleFetchComps() {
    if (!confirm) return;
    setCompsLoading(true);
    setCompsError(null);
    setCompsResult(null);
    try {
      const params: SoldCompsParams = { condition_type: compsConditionType };
      if (compsConditionType === "ungraded") {
        params.condition_ungraded = compsConditionUngraded;
      } else {
        params.grading_company = compsGradingCompany;
        if (compsGrade) params.grade = compsGrade;
      }
      let response = await getSoldComps(confirm.card.id, params);
      while (response.http_status === 202) {
        await new Promise((resolve) => setTimeout(resolve, 3000));
        response = await getSoldComps(confirm.card.id, params);
      }
      setCompsResult(response.data);
    } catch (e) {
      setCompsError(e instanceof Error ? e.message : "Failed to fetch sold comps");
    } finally {
      setCompsLoading(false);
    }
  }

  async function handleAddToInventory() {
    if (!confirm) return;
    setAdding(true);
    setAddError(null);
    try {
      await addInventoryItem({
        card_id: confirm.card.id,
        condition_type: conditionType,
        ...(conditionType === "ungraded"
          ? { condition_ungraded: conditionUngraded }
          : {
              grading_company: gradingCompany,
              grade,
              ...(gradingCompany === "other" ? { grading_company_other: gradingCompanyOther } : {}),
            }),
        asking_price: askingPrice || undefined,
        is_for_sale: isForSale,
        is_for_trade: isForTrade,
        quantity: parseInt(quantity) || 1,
        notes: notes || undefined,
      });
      const updated = await getInventory();
      setInventory(updated);
      setConfirm(null);
    } catch (err: unknown) {
      setAddError(err instanceof Error ? err.message : "Failed to add to inventory.");
    } finally {
      setAdding(false);
    }
  }

  const filteredInventory = useMemo(() => {
    if (!inventorySearch.trim()) return inventory;
    const q = inventorySearch.toLowerCase();
    return inventory.filter(
      (item) =>
        item.card_name.toLowerCase().includes(q) ||
        item.set_name.toLowerCase().includes(q) ||
        item.series_name.toLowerCase().includes(q) ||
        item.card_num.includes(q)
    );
  }, [inventory, inventorySearch]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Inventory</h1>

      {/* Add card section */}
      <div className="border rounded-lg p-4 space-y-3">
        <p className="text-sm font-medium text-muted-foreground">Add a card</p>

        {/* Search bar + camera button */}
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={query}
              onChange={(e) => { setQuery(e.target.value); if (showAdvanced) setShowAdvanced(false); }}
              placeholder="e.g. squirtle 170, jolteon prismatic, 034/193 ja…"
              className="w-full border rounded-md px-3 py-2 text-sm bg-background"
              disabled={showAdvanced}
            />
            {searching && !showAdvanced && (
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">…</span>
            )}
          </div>

          {/* Scan menu */}
          <div className="relative" ref={scanMenuRef}>
            <button
              onClick={() => setScanMenuOpen((o) => !o)}
              disabled={scanning}
              title="Scan a card"
              className="h-full px-3 border rounded-md bg-background hover:bg-muted transition-colors disabled:opacity-50 flex items-center justify-center"
            >
              {scanning ? (
                <span className="text-xs text-muted-foreground px-1">Scanning…</span>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                  <circle cx="12" cy="13" r="4"/>
                </svg>
              )}
            </button>

            {scanMenuOpen && (
              <div className="absolute right-0 top-full mt-1 w-52 bg-background border rounded-lg shadow-lg z-10 overflow-hidden">
                <button
                  className="w-full px-4 py-3 text-sm text-left hover:bg-muted transition-colors flex flex-col gap-0.5"
                  onClick={() => { quickScanInputRef.current?.click(); setScanMenuOpen(false); }}
                >
                  <span className="font-medium">Quick Scan</span>
                  <span className="text-xs text-muted-foreground">Google Vision OCR · fast</span>
                </button>
                <div className="border-t" />
                <button
                  className="w-full px-4 py-3 text-sm text-left hover:bg-muted transition-colors flex flex-col gap-0.5"
                  onClick={() => { claudeScanInputRef.current?.click(); setScanMenuOpen(false); }}
                >
                  <span className="font-medium">Claude Vision</span>
                  <span className="text-xs text-muted-foreground">AI identification · accurate</span>
                </button>
              </div>
            )}
          </div>

          <input
            ref={quickScanInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleScan(f, "quick");
              e.target.value = "";
            }}
          />
          <input
            ref={claudeScanInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleScan(f, "claude");
              e.target.value = "";
            }}
          />
        </div>

        {/* Advanced search toggle */}
        <div className="flex items-center justify-between">
          <button
            onClick={() => { setShowAdvanced((v) => !v); setSearchResults(null); setQuery(""); }}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {showAdvanced ? "← Smart search" : "Advanced search →"}
          </button>
          {showAdvanced && (
            <span className="text-xs text-muted-foreground">Fill any combination of fields</span>
          )}
        </div>

        {/* Advanced search panel */}
        {showAdvanced && (
          <div className="border rounded-md p-3 space-y-2 bg-muted/20">
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Name</label>
                <input
                  type="text"
                  value={advName}
                  onChange={(e) => setAdvName(e.target.value)}
                  placeholder="e.g. Charizard Ex"
                  className="w-full border rounded-md px-2 py-1.5 text-sm bg-background"
                  onKeyDown={(e) => e.key === "Enter" && handleAdvancedSearch()}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Number</label>
                <input
                  type="text"
                  value={advNum}
                  onChange={(e) => setAdvNum(e.target.value)}
                  placeholder="e.g. 170 or 034/193"
                  className="w-full border rounded-md px-2 py-1.5 text-sm bg-background"
                  onKeyDown={(e) => e.key === "Enter" && handleAdvancedSearch()}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Set Name</label>
                <input
                  type="text"
                  value={advSet}
                  onChange={(e) => setAdvSet(e.target.value)}
                  placeholder="e.g. Prismatic Evolutions"
                  className="w-full border rounded-md px-2 py-1.5 text-sm bg-background"
                  onKeyDown={(e) => e.key === "Enter" && handleAdvancedSearch()}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Language</label>
                <select
                  value={advLang}
                  onChange={(e) => setAdvLang(e.target.value)}
                  className="w-full border rounded-md px-2 py-1.5 text-sm bg-background"
                >
                  <option value="">Any</option>
                  <option value="en">English</option>
                  <option value="ja">Japanese</option>
                  <option value="fr">French</option>
                  <option value="de">German</option>
                  <option value="es">Spanish</option>
                  <option value="it">Italian</option>
                  <option value="pt">Portuguese</option>
                  <option value="ko">Korean</option>
                </select>
              </div>
            </div>
            <button
              onClick={handleAdvancedSearch}
              disabled={searching || (!advName && !advNum && !advSet)}
              className="w-full py-1.5 text-sm rounded-md bg-primary text-primary-foreground font-medium hover:opacity-90 transition-opacity disabled:opacity-40"
            >
              {searching ? "Searching…" : "Search"}
            </button>
          </div>
        )}

        {(searchError || scanError) && (
          <p className="text-xs text-destructive">{searchError ?? scanError}</p>
        )}

        {/* Search results */}
        {searchResults !== null && !confirm && (
          <div className="space-y-1 max-h-72 overflow-y-auto">
            {searchResults.length === 0 ? (
              <p className="text-sm text-muted-foreground px-1">No cards found.</p>
            ) : (
              searchResults.map((card) => (
                <CardRow key={card.id} card={card} onSelect={(c) => selectCard(c)} />
              ))
            )}
          </div>
        )}

        {/* Confirm form */}
        {confirm && (
          <div className="border rounded-lg p-4 space-y-4 bg-muted/30">
            {/* Card preview */}
            <div className="flex items-center gap-3">
              {confirm.card.image_url ? (
                <div className="w-14 aspect-[3/4] flex-shrink-0 rounded overflow-hidden border">
                  <img src={confirm.card.image_url} alt={confirm.card.name} className="w-full h-full object-contain" />
                </div>
              ) : (
                <div className="w-14 aspect-[3/4] flex-shrink-0 rounded border bg-muted" />
              )}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold">{confirm.card.name}</p>
                <p className="text-xs text-muted-foreground">{confirm.card.set_name} · #{confirm.card.card_num}</p>
                {confirm.card.rarity && <p className="text-xs text-muted-foreground">{confirm.card.rarity}</p>}
                {confirm.confidence != null && (
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {confirm.method ? `${confirm.method} · ` : ""}
                    {Math.round(confirm.confidence * 100)}% confidence
                  </p>
                )}
              </div>
              <button
                onClick={() => setConfirm(null)}
                className="text-xs text-muted-foreground hover:text-foreground self-start"
                title="Clear"
              >
                ✕
              </button>
            </div>

            {/* Condition picker */}
            <div className="space-y-2">
              <label className="text-xs text-muted-foreground">Condition</label>

              {/* Ungraded / Graded toggle */}
              <div className="flex gap-1">
                {(["ungraded", "graded"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => {
                      setConditionType(t);
                      setGrade("");
                    }}
                    className={`px-3 py-1 text-xs rounded-md border transition-colors capitalize ${
                      conditionType === t
                        ? "bg-foreground text-background border-foreground"
                        : "bg-background hover:bg-muted"
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>

              {/* Ungraded grade pills */}
              {conditionType === "ungraded" && (
                <div className="flex flex-wrap gap-1.5">
                  {UNGRADED_CONDITIONS.map((c) => (
                    <button
                      key={c.value}
                      onClick={() => setConditionUngraded(c.value)}
                      className={`px-2.5 py-1 text-xs rounded-md border transition-colors ${
                        conditionUngraded === c.value
                          ? "bg-foreground text-background border-foreground"
                          : "bg-background hover:bg-muted"
                      }`}
                    >
                      {c.label}
                    </button>
                  ))}
                </div>
              )}

              {/* Graded: company + grade picker */}
              {conditionType === "graded" && (
                <div className="space-y-2">
                  {/* Company selector */}
                  <div className="flex flex-wrap gap-1.5">
                    {GRADING_COMPANIES.map((co) => (
                      <button
                        key={co.value}
                        onClick={() => {
                          setGradingCompany(co.value);
                          setGrade("");
                          if (co.value !== "other") setGradingCompanyOther("");
                        }}
                        className={`px-2.5 py-1 text-xs rounded-md border transition-colors ${
                          gradingCompany === co.value
                            ? "bg-foreground text-background border-foreground"
                            : "bg-background hover:bg-muted"
                        }`}
                      >
                        {co.label}
                      </button>
                    ))}
                  </div>

                  {/* Other company — free text input */}
                  {gradingCompany === "other" && (
                    <input
                      type="text"
                      value={gradingCompanyOther}
                      onChange={(e) => setGradingCompanyOther(e.target.value)}
                      placeholder="Grading company name"
                      className="w-full border rounded-md px-3 py-2 text-sm bg-background"
                    />
                  )}

                  {/* Grade picker for known companies */}
                  {gradingCompany !== "other" && (
                    <div className="flex flex-wrap gap-1.5">
                      {gradeOptionsForCompany(gradingCompany).map((g) => (
                        <button
                          key={g.value}
                          onClick={() => setGrade(g.value)}
                          className={`px-2.5 py-1 text-xs rounded-md border transition-colors ${
                            grade === g.value
                              ? "bg-foreground text-background border-foreground"
                              : "bg-background hover:bg-muted"
                          }`}
                        >
                          {g.label}
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Grade free text for "other" company */}
                  {gradingCompany === "other" && (
                    <input
                      type="text"
                      value={grade}
                      onChange={(e) => setGrade(e.target.value)}
                      placeholder="Grade (e.g. 9, 9.5)"
                      className="w-full border rounded-md px-3 py-2 text-sm bg-background"
                    />
                  )}
                </div>
              )}
            </div>

            {/* Price + quantity */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Asking price</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">$</span>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={askingPrice}
                    onChange={(e) => setAskingPrice(e.target.value)}
                    placeholder="0.00"
                    className="w-full border rounded-md pl-6 pr-3 py-2 text-sm bg-background"
                  />
                </div>
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Quantity</label>
                <input
                  type="number"
                  min="1"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  className="w-full border rounded-md px-3 py-2 text-sm bg-background"
                />
              </div>
            </div>

            {/* For sale / trade */}
            <div className="flex gap-4">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={isForSale} onChange={(e) => setIsForSale(e.target.checked)} className="rounded" />
                For sale
              </label>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={isForTrade} onChange={(e) => setIsForTrade(e.target.checked)} className="rounded" />
                For trade
              </label>
            </div>

            {/* Notes */}
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Notes (optional)</label>
              <input
                type="text"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="e.g. light scratch on corner"
                className="w-full border rounded-md px-3 py-2 text-sm bg-background"
              />
            </div>

            {/* ---- Pricing debug ---- */}
            <div className="border rounded-lg p-3 space-y-2 bg-muted/20">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Raw Prices</p>
              <Button
                size="sm"
                variant="outline"
                onClick={handleFetchPricing}
                disabled={pricingLoading}
              >
                Fetch Data
              </Button>
              {pricingError && <p className="text-xs text-destructive">{pricingError}</p>}
              {(pricingLoading || (pricingResult !== null && (pricingResult as { http_status: number }).http_status === 202)) && (
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  <span>Fetching live price, this may take a moment…</span>
                </div>
              )}
              {pricingResult !== null && (pricingResult as { http_status: number }).http_status === 200 && (() => {
                const data = (pricingResult as { http_status: number; data: { nm_market_price: number; condition_estimates: { condition: string; label: string; estimated_price: number }[] } }).data;
                const estimates = data.condition_estimates.filter((e) => e.condition !== "nm");
                return (
                  <div className="space-y-1 text-xs">
                    <p className="font-medium">NM Market Price: ${data.nm_market_price.toFixed(2)}</p>
                    {estimates.map((e) => (
                      <p key={e.condition} className="text-muted-foreground">
                        {e.label} estimate: ${e.estimated_price.toFixed(2)}
                      </p>
                    ))}
                  </div>
                );
              })()}
            </div>

            <div className="border rounded-lg p-3 space-y-2 bg-muted/20">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Sold Comps</p>

              {/* Ungraded / Graded toggle */}
              <div className="flex gap-1">
                {(["ungraded", "graded"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => {
                      setCompsConditionType(t);
                      setCompsResult(null);
                      setCompsError(null);
                    }}
                    className={`px-2.5 py-1 text-xs rounded-md border transition-colors capitalize ${
                      compsConditionType === t
                        ? "bg-foreground text-background border-foreground"
                        : "bg-background hover:bg-muted"
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>

              {compsConditionType === "ungraded" && (
                <div className="flex flex-wrap gap-1.5">
                  {UNGRADED_CONDITIONS.map((c) => (
                    <button
                      key={c.value}
                      onClick={() => { setCompsConditionUngraded(c.value); setCompsResult(null); }}
                      className={`px-2.5 py-1 text-xs rounded-md border transition-colors ${
                        compsConditionUngraded === c.value
                          ? "bg-foreground text-background border-foreground"
                          : "bg-background hover:bg-muted"
                      }`}
                    >
                      {c.label}
                    </button>
                  ))}
                </div>
              )}

              {compsConditionType === "graded" && (
                <div className="space-y-2">
                  <div className="flex flex-wrap gap-1.5">
                    {GRADING_COMPANIES.filter((co) => co.value !== "other").map((co) => (
                      <button
                        key={co.value}
                        onClick={() => { setCompsGradingCompany(co.value); setCompsGrade(""); setCompsResult(null); }}
                        className={`px-2.5 py-1 text-xs rounded-md border transition-colors ${
                          compsGradingCompany === co.value
                            ? "bg-foreground text-background border-foreground"
                            : "bg-background hover:bg-muted"
                        }`}
                      >
                        {co.label}
                      </button>
                    ))}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {gradeOptionsForCompany(compsGradingCompany).map((g) => (
                      <button
                        key={g.value}
                        onClick={() => { setCompsGrade(g.value); setCompsResult(null); }}
                        className={`px-2.5 py-1 text-xs rounded-md border transition-colors ${
                          compsGrade === g.value
                            ? "bg-foreground text-background border-foreground"
                            : "bg-background hover:bg-muted"
                        }`}
                      >
                        {g.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <Button
                size="sm"
                variant="outline"
                onClick={handleFetchComps}
                disabled={compsLoading || (compsConditionType === "graded" && !compsGrade)}
              >
                {compsLoading ? "Fetching…" : "Fetch Data"}
              </Button>
              {compsError && <p className="text-xs text-destructive">{compsError}</p>}
              {compsLoading && (
                <p className="text-xs text-muted-foreground animate-pulse">Fetching sold listings…</p>
              )}
              {compsResult !== null && !compsLoading && (
                <div className="space-y-1.5">
                  <p className="text-xs text-muted-foreground">
                    {compsResult.total === 0
                      ? "No recent sales found."
                      : `${compsResult.total} recent sale${compsResult.total !== 1 ? "s" : ""}`}
                  </p>
                  {compsResult.comps.length > 0 && (() => {
                    const prices = compsResult.comps.map((c) => c.price);
                    const avg = prices.reduce((a, b) => a + b, 0) / prices.length;
                    const dates = compsResult.comps
                      .map((c) => c.sold_date ? new Date(c.sold_date) : null)
                      .filter((d): d is Date => d !== null);
                    const minDate = dates.length ? new Date(Math.min(...dates.map((d) => d.getTime()))) : null;
                    const maxDate = dates.length ? new Date(Math.max(...dates.map((d) => d.getTime()))) : null;
                    const fmt = (d: Date) => d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
                    return (
                      <>
                        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground px-0.5">
                          <span>Avg: <span className="font-medium text-foreground">${avg.toFixed(2)}</span></span>
                          <span>Range: <span className="font-medium text-foreground">${Math.min(...prices).toFixed(2)} – ${Math.max(...prices).toFixed(2)}</span></span>
                          {minDate && maxDate && (
                            <span>Dates: <span className="font-medium text-foreground">{fmt(minDate)} – {fmt(maxDate)}</span></span>
                          )}
                        </div>
                        <div className="border rounded-md overflow-hidden">
                      <table className="w-full text-xs">
                        <thead className="bg-muted text-muted-foreground">
                          <tr>
                            <th className="text-left px-2 py-1.5 font-medium">Date</th>
                            <th className="text-left px-2 py-1.5 font-medium">Title</th>
                            <th className="text-left px-2 py-1.5 font-medium">Condition</th>
                            <th className="text-left px-2 py-1.5 font-medium">Sale Type</th>
                            <th className="text-right px-2 py-1.5 font-medium">Price</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                          {compsResult.comps.map((comp) => (
                            <tr
                              key={comp.id}
                              className="hover:bg-muted/40 transition-colors cursor-pointer"
                              onClick={() => window.open(comp.listing_url, "_blank", "noopener,noreferrer")}
                            >
                              <td className="px-2 py-1.5 whitespace-nowrap text-muted-foreground">
                                {comp.sold_date
                                  ? new Date(comp.sold_date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
                                  : "—"}
                              </td>
                              <td className="px-2 py-1.5 max-w-[180px]">
                                <span className="truncate block text-foreground" title={comp.title}>
                                  {comp.title}
                                </span>
                              </td>
                              <td className="px-2 py-1.5 whitespace-nowrap">
                                {comp.condition_type === "graded" && comp.grading_company && comp.grade ? (
                                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300 font-medium">
                                    {comp.grading_company.toUpperCase()} {comp.grade}
                                  </span>
                                ) : comp.condition_ungraded ? (
                                  <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                                    {comp.condition_ungraded}
                                  </span>
                                ) : (
                                  <span className="text-muted-foreground">—</span>
                                )}
                              </td>
                              <td className="px-2 py-1.5 whitespace-nowrap">
                                {comp.sale_type === "buy_now" && (
                                  <span className="inline-flex px-1.5 py-0.5 rounded bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300 font-medium">Buy Now</span>
                                )}
                                {comp.sale_type === "auction" && (
                                  <span className="inline-flex px-1.5 py-0.5 rounded bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300 font-medium">Auction</span>
                                )}
                                {comp.sale_type === "obo" && (
                                  <span className="inline-flex px-1.5 py-0.5 rounded bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300 font-medium">OBO</span>
                                )}
                                {!comp.sale_type && <span className="text-muted-foreground">—</span>}
                              </td>
                              <td className="px-2 py-1.5 text-right font-medium whitespace-nowrap">
                                {comp.currency === "USD" ? "$" : comp.currency}{Number(comp.price).toFixed(2)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                      </>
                    );
                  })()}
                  <details className="mt-2">
                    <summary className="text-xs text-muted-foreground cursor-pointer select-none hover:text-foreground">Raw JSON</summary>
                    <pre className="mt-1 text-xs bg-muted border rounded p-2 overflow-auto max-h-64 whitespace-pre-wrap break-all">
                      {JSON.stringify(compsResult, null, 2)}
                    </pre>
                  </details>
                </div>
              )}
            </div>
            {/* ---- end sold comps ---- */}

            {addError && <p className="text-xs text-destructive">{addError}</p>}

            <div className="flex gap-2 justify-end">
              <Button variant="outline" size="sm" onClick={() => setConfirm(null)}>
                Cancel
              </Button>
              <Button size="sm" onClick={handleAddToInventory} disabled={adding}>
                {adding ? "Adding…" : "Add to inventory"}
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Inventory list */}
      <div className="space-y-3">
        <p className="text-sm font-medium text-muted-foreground">
          {loadingInventory ? "Loading…" : `${inventory.length} card${inventory.length !== 1 ? "s" : ""}`}
        </p>

        <input
          type="text"
          placeholder="Filter inventory..."
          value={inventorySearch}
          onChange={(e) => setInventorySearch(e.target.value)}
          className="w-full border rounded-md px-3 py-2 text-sm bg-background"
        />

        {!loadingInventory && filteredInventory.length === 0 && (
          <p className="text-sm text-muted-foreground">
            {inventorySearch ? "No cards match your filter." : "No cards in inventory yet."}
          </p>
        )}

        <div className="space-y-1">
          {filteredInventory.map((item) => (
            <InventoryRow key={item.id} item={item} />
          ))}
        </div>
      </div>
    </div>
  );
}
