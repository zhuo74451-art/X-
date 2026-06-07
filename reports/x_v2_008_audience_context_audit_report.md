# X v2-008 Audience Context Audit Report

- **generated_at_utc**: 2026-06-07T17:29:08+00:00
- **audited_count**: 2
- **model_calls_made**: 0

| event_id | score | jargon | riddles | action |
|----------|-------|--------|---------|--------|
| real_v006_rss_f12050b18970 | 8 | 0 | 0 | KEEP |
| real_v006_rss_d30124a258e4 | 0 | 3 | 1 | DEMOTE_TO_INSIDER_ONLY |

## real_v006_rss_f12050b18970

- **action**: KEEP
- **audience_context_score**: 8/10
- **jargon_count**: 0
- **unexplained_entities**: []
- **riddle_phrases**: []
- **overstatements**: []
- **user_entry_test**: 2/4
- **ordinary_user_understands**: True
- **扣分原因**: user_entry_test=2/4 answered (-2) details={'what_happened': True, 'why_important': False, 'user_impact': False, 'controversy': True}

---

## real_v006_rss_d30124a258e4

- **action**: DEMOTE_TO_INSIDER_ONLY
- **audience_context_score**: 0/10
- **jargon_count**: 3
- **unexplained_entities**: ['EF', 'Lubin', 'Consensys']
- **riddle_phrases**: ['耐人寻味']
- **overstatements**: []
- **user_entry_test**: 2/4
- **ordinary_user_understands**: False
- **扣分原因**: jargon_count=3 terms=['EF', 'Lubin', 'Consensys'] (-6); riddles=['耐人寻味'] (-2); user_entry_test=2/4 answered (-2) details={'what_happened': True, 'why_important': False, 'user_impact': False, 'controversy': True}

---

