# Menteso Overdue Reminder Agent

Isolated follow-up workflow for overdue invoices in the **Menteso, Inc.** Wave
business only. The agent owns an overdue invoice when no Wave reminder flow is
configured, or after all reminders in a configured Wave flow have been sent.
While any Wave reminder is pending, Wave owns the invoice and the agent waits.
Paid or otherwise resolved invoices are excluded on every scan. The agent
groups invoices by Wave customer and operates in test mode until an authorized
approver enables live mode. Real-client delivery is forbidden in test mode.

Authorized live-mode approvers: shweta@menteso.com, sajan@menteso.com,
azam@menteso.com.
