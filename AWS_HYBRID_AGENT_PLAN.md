# Menteso OS Hybrid Local + AWS Agent Plan

## 1. Goal

Build one Menteso OS that can run agents in two locations:

- **Local Windows server** for always-on, light, private, and low-cost work.
- **AWS EC2 worker** for heavy or temporary workloads that need more CPU, memory, bandwidth, or parallel execution.

The dashboard must show and control every agent from one place regardless of where the agent runs. AWS compute must be used only when a job needs it so that billing stays predictable.

## 2. First AWS Worker

Create one EC2 `t3.xlarge` instance in the same AWS region as the existing Menteso gateway.

Expected instance capacity:

- 4 vCPUs
- 16 GiB memory
- Burstable CPU performance

Important: T3 is appropriate for variable workloads, but it is not automatically the cheapest choice for continuous heavy CPU work. In Unlimited mode, sustained CPU above the earned credit level can create surplus-credit charges. After collecting real workload metrics, compare `t3.xlarge` with a non-burstable compute or general-purpose instance before committing to long-running heavy processing.

## 3. Target Architecture

```text
                         os.menteso.com
                                |
                         AWS Caddy gateway
                                |
                    Menteso OS control dashboard
                                |
                +---------------+---------------+
                |                               |
          Local agent runner              AWS agent runner
          Windows office server           EC2 t3.xlarge worker
                |                               |
       light/private/always-on            heavy/parallel/batch
                +---------------+---------------+
                                |
                     shared job/status service
                                |
                   PostgreSQL + artifact storage
```

The web dashboard is the **control plane**. Agent runners are the **workers**. The dashboard must never depend on an agent process running inside the same machine.

## 4. Agent Placement Policy

Each registered agent will declare a runtime policy:

```json
{
  "execution_target": "local | aws | auto",
  "workload_class": "light | medium | heavy",
  "max_runtime_minutes": 60,
  "max_parallel_jobs": 1,
  "requires_private_local_files": false,
  "allow_aws_fallback": true
}
```

Placement rules:

| Work type | Default location | Reason |
|---|---|---|
| Dashboard, scheduler, heartbeat, deployment checks | Local | Lightweight and always needed |
| Jobs using private local-only files/devices | Local | Avoid unnecessary data transfer |
| Small SEO research or one article | Local | Low compute cost |
| Large SEO batches and parallel generation | AWS | Temporary parallel capacity |
| Large PCT Excel/PDF processing | AWS | CPU, memory, network, and browser workload |
| Small PCT test or debugging run | Local | Faster development feedback |
| Unknown workload with `auto` policy | Local first | Escalate to AWS only after a threshold |

Initial assignment:

- **PCT Agent:** `auto`; local for testing and small files, AWS for large batches.
- **SEO Posting Agent:** `auto`; local for scheduled single posts, AWS for backfills and multi-workspace batches.

## 5. Job Routing

Add a central job queue with these states:

`queued -> assigned -> running -> validating -> completed | failed | cancelled`

Each job record must contain:

- Job ID, agent, workspace, user, and creation time
- Requested and selected execution target
- Input references, not unrestricted local paths
- Runtime, retry count, progress, and heartbeat
- Estimated and actual compute usage
- Output artifact locations
- Error and validation results

The local and AWS runners poll only for jobs assigned to their runner ID. A runner sends a heartbeat every 30-60 seconds. If the heartbeat expires, the control plane marks the job interrupted and applies its retry policy.

Recommended first implementation: PostgreSQL-backed queue with row locking. Add Redis only when concurrency or throughput proves it is needed.

## 6. Data and Artifact Handling

- Store job metadata, status, and agent history in PostgreSQL.
- Store large uploads, PDFs, generated images, reports, and logs in a private S3 bucket.
- Use short-lived presigned S3 URLs for worker input and output transfer.
- Keep secrets in AWS Secrets Manager or SSM Parameter Store on AWS; keep local secrets in protected environment configuration.
- Never copy the full local `.env` file to AWS.
- Give the EC2 instance an IAM role with access only to its required S3 paths, queue resources, logs, and secrets.
- Encrypt EBS and S3 data and enforce HTTPS/TLS for all worker traffic.

## 7. AWS Worker Lifecycle

The AWS worker should support three operating modes:

1. **Stopped:** default when there are no AWS jobs. EBS storage still costs money, but instance compute does not.
2. **Starting/idle:** instance is booting or waiting briefly for work.
3. **Busy:** one or more approved jobs are executing.

Lifecycle rules:

- Start the instance when an approved AWS job enters the queue.
- Do not accept jobs until the runner health check succeeds.
- Stop after 15-30 idle minutes.
- Enforce a maximum job runtime and terminate orphan child processes.
- Do not stop while an active job is writing output.
- Use EC2 stop, not terminate, for the persistent worker.
- Add an emergency stop control in the admin dashboard.
- Initially keep instance start/stop approval manual; automate it only after job recovery is tested.

## 8. Billing and Safety Controls

Implement all of the following before enabling automatic AWS execution:

- AWS Budget with monthly thresholds at 50%, 80%, and 100%.
- Email alerts and a dashboard warning at every threshold.
- Cost allocation tags: `Project=MentesoOS`, `Role=AgentWorker`, `Environment=Production`.
- Per-agent daily and monthly runtime limits.
- Per-workspace usage totals.
- Maximum parallel AWS jobs.
- Instance-type allowlist; agents cannot request a larger instance directly.
- Hard kill timeout for stuck jobs.
- Idle shutdown.
- CloudWatch alarms for CPU, memory, disk, failed health checks, and unexpected network usage.
- Record estimated AWS cost against each job.
- At the configured hard budget limit, block new AWS jobs and continue safe local work. Do not automatically terminate an active job in the middle of data writes.

## 9. Networking

- Keep the existing AWS Caddy gateway for `os.menteso.com` and `server.menteso.com`.
- Do not expose the agent runner API publicly.
- Prefer private VPC networking between AWS services.
- Connect the local server to AWS through a persistent outbound WireGuard/Tailscale-style private tunnel or a carefully restricted SSH tunnel.
- Restrict SSH to the office public IP or use AWS Systems Manager Session Manager so port 22 does not need to remain publicly open.
- Use signed runner authentication and rotate credentials.

## 10. Reliability Rules

- Every job must be idempotent or have a resume checkpoint.
- Workers must save progress at safe boundaries.
- A runner loss must not lose the job record.
- Retry only failures classified as transient.
- Do not run the same job on local and AWS workers simultaneously unless explicitly designed as a distributed job.
- Validate outputs before marking a job completed.
- Preserve logs centrally even if the EC2 worker is stopped.

## 11. Implementation Phases

### Phase 0 - Restore the current foundation

- Restore `os.menteso.com` and its local service on port 8010.
- Restore secure connectivity to the AWS gateway.
- Document and rotate administrative credentials.
- Back up the current application, configuration, database, and agent memory.

### Phase 1 - Refactor Menteso OS into control plane and runner

- Define the job and runner database schemas.
- Add runner registration and heartbeat endpoints.
- Move direct in-process agent launching behind a runner interface.
- Implement the local runner first.
- Preserve current dashboard run, stop, progress, and SSE behavior.

### Phase 2 - Provision the AWS worker

- Create the t3.xlarge in a private subnet where practical.
- Attach an encrypted EBS volume and least-privilege IAM role.
- Install Python, Playwright/browser dependencies, Git, and the Menteso runner service.
- Store deployment configuration outside the Git repository.
- Register the runner with Menteso OS and verify heartbeats.

### Phase 3 - Add remote job execution

- Add PostgreSQL job claiming and locking.
- Add S3 input/output transfer.
- Run a small test job on AWS.
- Test progress streaming, cancellation, timeout, retry, validation, and artifact download.
- Confirm that stopping the EC2 instance does not corrupt a job.

### Phase 4 - Add automatic placement and cost controls

- Add agent runtime policies and workload thresholds.
- Add manual Local/AWS/Auto selection in the admin dashboard.
- Add budget, runtime, concurrency, and idle-stop rules.
- Show target, runtime, and estimated cost on each job.
- Enable automatic AWS start/stop only after manual tests pass.

### Phase 5 - Optimize using real measurements

- Measure CPU, memory, duration, S3 transfer, and cost for each agent/job type.
- Adjust the small/large workload thresholds.
- Compare t3.xlarge cost and performance with non-burstable alternatives for sustained work.
- Consider Spot Instances only for checkpointed, restartable batch jobs.
- Consider separate specialized workers only after utilization justifies them.

## 12. Definition of Done

The hybrid system is complete when:

- The same dashboard can run an agent locally or on AWS.
- Local and AWS runners report health and capacity.
- Jobs survive dashboard or worker restarts.
- Inputs and outputs transfer securely without sharing unrestricted folders.
- AWS automatically stops after the configured idle period.
- Budget and runtime limits prevent uncontrolled usage.
- Every job shows where it ran, how long it ran, and its estimated cost.
- PCT and SEO agents both pass local and AWS end-to-end tests.

## 13. Decisions Required Before Provisioning

- AWS region and whether the existing gateway VPC will be reused.
- Monthly AWS budget and hard-stop threshold.
- Maximum allowed AWS runtime per day.
- Idle shutdown delay.
- PostgreSQL location and backup policy.
- S3 retention period for uploads and outputs.
- Whether the first worker will be manually or automatically started.
- Which workload size should trigger PCT and SEO jobs to move to AWS.

## 14. AWS References

- T3 instances: https://aws.amazon.com/ec2/instance-types/t3/
- Burstable Unlimited mode: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-performance-instances-unlimited-mode.html
- AWS Budgets controls: https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-controls.html
- Systems Manager Session Manager: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html
