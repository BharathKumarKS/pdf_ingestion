#!/usr/bin/env bash
# Chain: wait for the v3_judged_full eval to finish, then run T3 (the lane-complete A/B).
# Serialised on purpose: the eval and T3 both hammer the SV cluster, and concurrent runs produced
# read-timeouts on 2026-11-02. Launched detached by the agent.
set -u
REPO=/Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/Project/Team_Project/pdf_ingestion
cd "$REPO"
LOG=logs/p1/step10/t3_after_eval.log
echo "$(date '+%F %T') chain started; waiting for the eval" >> "$LOG"

while pgrep -f "scripts/evaluate_rag.py" >/dev/null 2>&1; do sleep 60; done
echo "$(date '+%F %T') eval finished; starting T3" >> "$LOG"

bash logs/p1/step10/run_t3.sh >> "$LOG" 2>&1
echo "$(date '+%F %T') T3 finished rc=$?" >> "$LOG"
