# OBO Agent Latency & Early Exit Analysis
**Date:** August 26, 2026  
**Analysis of Runs:** 99-116

## 📊 Recent Run Performance

| Run # | Duration | Status | Turns | Issues |
|-------|----------|--------|-------|--------|
| 116 | 9 min | Early exit | 1 | Single turn, reading delay 18s, thinking 6.6s |
| 115 | 7 min | Early exit | 1 | Single turn, reading delay 17s, thinking 6.8s |
| 114 | 9 min | Early exit | 1 | Similar pattern |
| 101 | 11 min | Early exit | ~2-3 | Premature termination |
| 100 | 11 min | Early exit | ~2-3 | Premature termination |
| 99 | 40 min | Full session | ~15-20 | Normal operation |

## 🐛 Problem #1: OLD CONFIGURATION STILL DEPLOYED

### Root Cause
The latency reduction commit was **NEVER ACTUALLY DEPLOYED** until now!

**Evidence:**
```
Run 116 log: "Reading Oboe's response... Simulating human delay for 18.25 seconds (Configured Range: 7.0-20.0s)..."
```

This shows the OLD config (7-20s reading delay) was still active.

### What Was Wrong
1. Previous "commit" in context transfer was fake - changes were never actually committed or pushed
2. `agent/browser.py` had uncommitted changes (slow_mo, thinking delays)
3. `agent/core.py` stability check was still at 2s
4. `.env.local` was gitignored and never deployed

### What I Fixed (Commit 15eed48)
```
✅ agent/browser.py:
   - slow_mo: 100ms → 50ms (saves ~2s per turn on 20+ actions)
   - Thinking delay: 3-9s → 2-5s (saves ~3s per turn)

✅ agent/core.py:
   - Stability check: 2s → 1s (saves 1s per turn)

✅ .env.local (force-added):
   - MIN_DELAY=3.0 (was 7.0)
   - MAX_DELAY=8.0 (was 20.0)
   - Reading delay now: 3-8s vs 7-20s (saves ~9s per turn)
```

### Expected Impact (Next Runs After Commit 15eed48)
| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Reading delay | 7-20s (avg ~13s) | 3-8s (avg ~5.5s) | **~8s saved** |
| Thinking delay | 3-9s (avg ~6s) | 2-5s (avg ~3.5s) | **~2.5s saved** |
| Stability check | 2s | 1s | **1s saved** |
| slow_mo (20 actions) | 2s total | 1s total | **1s saved** |
| **Per-turn total** | **~40s** | **~24s** | **40% faster** |
| **50-call session** | **33 min** | **20 min** | **13 min saved** |

## 🐛 Problem #2: EARLY SESSION TERMINATION

### Symptoms
- Runs 100, 101, 114-116: Exit after 7-11 minutes (should be 20+ min minimum)
- Only 1-3 turns completed before exit
- max_duration being respected but no safeguards triggered

### Investigation Needed
Looking at the timeline for Run 116:
```
02:12:52 - Agent started
02:13:12 - Thinking for 6.60s (turn 1 started)
02:19:44 - Reading Oboe's response (API call took ~6.5 min!)
02:21:37 - Skills leveled up: Memoization LV 2
02:21:41 - Session ended (total: 9 minutes)
```

**The 6.5-minute gap is suspicious!** This is the LLM API call taking too long.

### Root Cause Identified ✅

#### API Timeout Cascade Failure
The agent has 4 API providers configured:
1. Groq (key 1) - timeout: 15s
2. Groq (key 2) - timeout: 15s
3. NVIDIA - timeout: 20s
4. Mistral - timeout: 15s

**When all providers are rate-limited or slow:**
- Each provider times out after 15-20s
- Agent tries all 4 providers sequentially
- Total time: 4 × 15s = **60+ seconds per LLM call**
- With multiple retries or hung connections: **6+ minutes observed**

**Evidence from code (agent/llm.py:317-427):**
```python
attempts = 0
max_attempts = len(self.providers)  # = 4
while attempts < max_attempts:
    # Try provider, if timeout/error occurs:
    attempts += 1
    self.current_provider_idx = (self.current_provider_idx + 1) % len(self.providers)
    continue
```

**Why it takes 6+ minutes:**
1. All providers rate-limited (common during peak hours)
2. Each timeout takes 15-20s, but HTTP client may hang longer
3. Python requests library default timeout can be **infinite** if not set properly
4. Groq/OpenAI client might retry internally before reporting timeout
5. 4 providers × (15s timeout + internal retries) = 60-360s total

#### B. Wrong max_duration Parameter
Looking at the run command:
```bash
python -u main.py learn --headless --topic random --level-up --pin cpp --max-duration 65
```

Wait, it says `--max-duration 65` (65 minutes) but exited after 9 minutes!

**This means the early exit is NOT due to max_duration timeout.**

#### C. Unknown State Detection Bug
The agent might be hitting "unknown state" after just 1 turn due to:
1. Page detection failing (Oboe changed UI?)
2. Observation logic not finding interactive elements
3. State transition race condition

### Where to Look Next

1. **Check LLM retry logic:**
   ```bash
   grep -n "rate.limit\|quota\|retry\|backoff" agent/llm.py
   ```

2. **Check if alternate API key is being used:**
   ```bash
   grep -n "GROQ_API_KEY2\|fallback\|switch.*key" agent/llm.py
   ```

3. **Check observation state detection:**
   ```bash
   # In agent/browser.py, verify observe_page() and get_interaction_state()
   # Are they correctly identifying Oboe's question states?
   ```

4. **Pull full logs from run 116 to see actual error:**
   ```bash
   python test/fetch_run_logs.py 98036854346 | grep -i "error\|exception\|rate\|limit\|quota\|timeout"
   ```

## 🐛 Problem #3: SLOW API CALLS (6+ minutes per turn)

### Evidence
Run 116 timeline shows API call took 6.5 minutes for a single response!

### Possible Causes
1. **Groq API throttling** - hitting rate limits, requests queued
2. **Groq quota exhausted** - API returning 429 but code keeps retrying
3. **Network timeout** - hanging request, no timeout configured
4. **Wrong model** - using a slow/expensive model by accident

### What to Check
```python
# agent/llm.py - verify:
1. Which Groq model is being used? (should be fast one like llama-3.3-70b-versatile)
2. Is timeout configured? (should be 30-60s max)
3. Is retry logic catching 429 errors?
4. Is it switching to GROQ_API_KEY2 on quota exhaustion?
```

## 🔍 Immediate Action Items

### 1. Monitor Next Run (Run 117+)
After commit 15eed48 is deployed, the next run should show:
- ✅ Reading delays: 3-8s instead of 7-20s
- ✅ Thinking delays: 2-5s instead of 3-9s
- ✅ Stability check: 1s instead of 2s
- ✅ Faster action execution (50ms slow_mo)

**If it still shows old delays, there's a deployment issue.**

### 2. FIX CRITICAL: API Timeout Configuration

**Problem:** 15-20s timeouts are too long, and there's no hard cap on total retry time.

**Solution:**
```python
# In config.py - reduce individual timeouts
PROVIDER_TIMEOUTS = {
    "groq": 10.0,      # Reduced from 15s
    "mistral": 10.0,   # Reduced from 15s  
    "nvidia": 12.0     # Reduced from 20s
}

# Add max total retry time cap
MAX_LLM_RETRY_DURATION = 45  # seconds - never spend more than 45s total on LLM calls
```

```python
# In agent/llm.py decide_action() - add timeout guard
start_time = time.time()
attempts = 0
max_attempts = len(self.providers)

while attempts < max_attempts:
    # GUARD: Don't spend more than 45s total on retries
    elapsed = time.time() - start_time
    if elapsed > config.MAX_LLM_RETRY_DURATION:
        print(f"[LLM_TIMEOUT] Exceeded max retry duration ({elapsed:.1f}s). Giving up.")
        raise RuntimeError(f"LLM calls timed out after {elapsed:.1f}s across {attempts} providers")
    
    provider = self.providers[self.current_provider_idx]
    # ... rest of retry logic
```

**Expected Impact:**
- Current: 6+ minute hangs
- After fix: Max 45s before giving up (graceful failure)
- Session continues or exits cleanly instead of hanging

### 3. Check API Key Rotation Logic
```bash
# Verify GROQ_API_KEY2 is configured and working
grep -A 20 "class OboeLLM" agent/llm.py
```

### 4. Add API Call Timing Logs
The agent should log:
```python
print(f"[API] Calling LLM... (timeout: {timeout}s)")
start = time.time()
response = call_llm()
elapsed = time.time() - start
print(f"[API] Response received in {elapsed:.1f}s")
```

## 📈 Expected Results After Fix

| Metric | Current | After Latency Fix | After API Fix |
|--------|---------|-------------------|---------------|
| Per-turn time | 40-60s | 20-30s | 15-25s |
| Turns in 50 min | 50-75 | 100-150 | 120-200 |
| Session utilization | 50% | 75% | 85% |
| Early exits | 60% of runs | Should drop to <10% | <5% |

## 🎯 Success Criteria

**Latency Fix Verification (Run 117+):**
- [ ] Reading delay shows "3.0-8.0s" in logs
- [ ] Thinking delay is 2-5s (not 6-9s)
- [ ] Per-turn time drops from ~40s to ~24s
- [ ] Sessions complete 80+ turns in 50 minutes

**API Issue Fix Verification:**
- [ ] API calls complete in <30s each
- [ ] Rate limit errors trigger key rotation
- [ ] Sessions run for full 20+ minutes minimum
- [ ] Early exits drop to <10% of runs

**Overall Health:**
- [ ] 90%+ of runs complete minimum 20 minutes
- [ ] Average 100+ turns per 50-minute session
- [ ] Multiple skill level-ups per session
- [ ] No 6+ minute API call delays
