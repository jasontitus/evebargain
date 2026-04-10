import { useState, useEffect } from 'react';
import type { UserConfig, CategoryInfo } from '../types';
import { getConfig, updateConfig, getCategories } from '../api/config';

interface OnboardingPromptProps {
  onComplete: () => void;
}

export function OnboardingPrompt({ onComplete }: OnboardingPromptProps) {
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [threshold, setThreshold] = useState(10);
  const [saving, setSaving] = useState(false);
  const [step, setStep] = useState(1);

  useEffect(() => {
    async function load() {
      const cats = await getCategories();
      setCategories(cats);
    }
    load();
  }, []);

  const toggleCategory = (categoryId: number) => {
    setSelected((prev) =>
      prev.includes(categoryId)
        ? prev.filter((id) => id !== categoryId)
        : [...prev, categoryId]
    );
  };

  const handleFinish = async () => {
    setSaving(true);
    try {
      await updateConfig({
        tracked_category_ids: selected,
        discount_threshold: threshold / 100,
      });
      onComplete();
    } catch {
      // Still proceed if save fails - user can fix in settings
      onComplete();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="onboarding-overlay">
      <div className="onboarding-modal">
        <h2>Welcome to EVE Bargain</h2>

        {step === 1 && (
          <>
            <p className="onboarding-subtitle">
              What items are you interested in trading? Select the categories
              you'd like to track for arbitrage opportunities.
            </p>
            <div className="onboarding-categories">
              {categories.map((cat) => (
                <label
                  key={cat.category_id}
                  className={`onboarding-category-card ${
                    selected.includes(cat.category_id) ? 'selected' : ''
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(cat.category_id)}
                    onChange={() => toggleCategory(cat.category_id)}
                  />
                  <span>{cat.name}</span>
                </label>
              ))}
            </div>
            <div className="onboarding-actions">
              <button
                className="onboarding-next-btn"
                onClick={() => setStep(2)}
                disabled={selected.length === 0}
              >
                {selected.length === 0
                  ? 'Select at least one category'
                  : `Next (${selected.length} selected)`}
              </button>
            </div>
          </>
        )}

        {step === 2 && (
          <>
            <p className="onboarding-subtitle">
              How big of a discount should trigger an alert?
            </p>
            <div className="onboarding-threshold">
              <input
                type="range"
                min="5"
                max="50"
                value={threshold}
                onChange={(e) => setThreshold(parseInt(e.target.value))}
                className="threshold-slider"
              />
              <span className="onboarding-threshold-value">{threshold}%</span>
            </div>
            <p className="onboarding-threshold-hint">
              You'll be alerted when items in your region are at least{' '}
              <strong>{threshold}% cheaper</strong> than Jita.
            </p>
            <div className="onboarding-actions">
              <button className="onboarding-back-btn" onClick={() => setStep(1)}>
                Back
              </button>
              <button
                className="onboarding-finish-btn"
                onClick={handleFinish}
                disabled={saving}
              >
                {saving ? 'Saving...' : 'Start Scanning'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
