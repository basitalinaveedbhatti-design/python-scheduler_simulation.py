import csv
import os
from dataclasses import dataclass
from typing import Optional, List

import matplotlib.pyplot as plt


# ==========================================================
# 1. DATA STRUCTURES
# ==========================================================

@dataclass(frozen=True)
class Task:
    name: str
    period: int              # milliseconds
    wcet: int                # Worst-Case Execution Time (ms)
    criticality: str
    overload_only: bool = False


@dataclass
class Job:
    uid: int
    task: Task
    release: int
    deadline: int
    remaining: int
    completed_at: Optional[int] = None
    missed: bool = False


# ==========================================================
# 2. AUTOMOTIVE-INSPIRED TASK SET
# ==========================================================

NORMAL_TASKS = [
    Task("Brake",       5,   1,  "High"),
    Task("Steering",   10,   1,  "High"),
    Task("Engine",     20,   2,  "High"),
    Task("Sensor",     50,   5,  "Medium"),
    Task("Diagnostics", 100, 20, "Low"),
]


# Temporary burst workload used to create overload
OVERLOAD_TASK = Task(
    "Burst",
    period=5,
    wcet=2,
    criticality="Medium",
    overload_only=True
)


# ==========================================================
# 3. SIMULATION SETTINGS
# ==========================================================

SIM_TIME = 5000           # total simulation time (ms)

OVERLOAD_START = 2000     # overload begins
OVERLOAD_END = 2500       # overload ends


# ==========================================================
# 4. UTILISATION
# ==========================================================

def utilisation(tasks):
    return sum(task.wcet / task.period for task in tasks)


# ==========================================================
# 5. SCHEDULER SIMULATION
# ==========================================================

def simulate(policy: str):

    ready: List[Job] = []
    all_jobs: List[Job] = []

    uid = 0

    preemptions = 0
    miss_count = 0

    recovery_time = None

    previous_running: Optional[Job] = None

    timeline = []
    cumulative_misses = []


    # ------------------------------------------------------
    # Scheduling priority rule
    # ------------------------------------------------------

    def priority_key(job):

        # RMS:
        # shorter period = higher priority
        if policy == "RMS":
            return (
                job.task.period,
                job.release,
                job.uid
            )

        # EDF:
        # earliest absolute deadline = highest priority
        elif policy == "EDF":
            return (
                job.deadline,
                job.task.period,
                job.release,
                job.uid
            )

        else:
            raise ValueError(
                "Scheduler must be RMS or EDF"
            )


    # ======================================================
    # MAIN SIMULATION LOOP
    # ======================================================

    for time in range(SIM_TIME):

        # --------------------------------------------------
        # Release normal periodic jobs
        # --------------------------------------------------

        for task in NORMAL_TASKS:

            if time % task.period == 0:

                uid += 1

                job = Job(
                    uid=uid,
                    task=task,
                    release=time,
                    deadline=time + task.period,
                    remaining=task.wcet
                )

                ready.append(job)
                all_jobs.append(job)


        # --------------------------------------------------
        # Introduce transient overload
        # --------------------------------------------------

        if OVERLOAD_START <= time < OVERLOAD_END:

            if (
                (time - OVERLOAD_START)
                % OVERLOAD_TASK.period == 0
            ):

                uid += 1

                job = Job(
                    uid=uid,
                    task=OVERLOAD_TASK,
                    release=time,
                    deadline=time + OVERLOAD_TASK.period,
                    remaining=OVERLOAD_TASK.wcet
                )

                ready.append(job)
                all_jobs.append(job)


        # --------------------------------------------------
        # Check for deadline misses
        # --------------------------------------------------

        for job in ready:

            if (
                job.remaining > 0
                and time >= job.deadline
                and not job.missed
            ):

                job.missed = True
                miss_count += 1


        # --------------------------------------------------
        # CPU scheduling
        # --------------------------------------------------

        if ready:

            current = min(
                ready,
                key=priority_key
            )


            # ----------------------------------------------
            # Detect preemption
            # ----------------------------------------------

            if (
                previous_running is not None
                and previous_running.uid != current.uid
                and previous_running in ready
                and previous_running.remaining > 0
            ):

                preemptions += 1


            # ----------------------------------------------
            # Execute job for 1 ms
            # ----------------------------------------------

            current.remaining -= 1

            timeline.append(
                (time, current.task.name)
            )


            # ----------------------------------------------
            # Job completed
            # ----------------------------------------------

            if current.remaining == 0:

                current.completed_at = time + 1


                # Check whether completion was late
                if (
                    current.completed_at
                    > current.deadline
                    and not current.missed
                ):

                    current.missed = True
                    miss_count += 1


                ready.remove(current)

                previous_running = None

            else:

                previous_running = current


        else:

            timeline.append(
                (time, "IDLE")
            )

            previous_running = None


        # --------------------------------------------------
        # Save cumulative misses
        # --------------------------------------------------

        cumulative_misses.append(
            (time, miss_count)
        )


        # --------------------------------------------------
        # Recovery measurement
        # --------------------------------------------------

        if (
            time + 1 >= OVERLOAD_END
            and recovery_time is None
        ):

            backlog_exists = any(

                job.remaining > 0
                and job.release < OVERLOAD_END

                for job in ready
            )

            if not backlog_exists:

                recovery_time = (
                    time + 1
                ) - OVERLOAD_END


    # ======================================================
    # CALCULATE RESULTS
    # ======================================================

    finished_jobs = [
        job
        for job in all_jobs
        if job.completed_at is not None
    ]


    response_times = [

        job.completed_at - job.release

        for job in finished_jobs
    ]


    tardiness = [

        max(
            0,
            job.completed_at - job.deadline
        )

        for job in finished_jobs
    ]


    deadline_misses = sum(

        1

        for job in all_jobs

        if job.missed
    )


    deadline_miss_ratio = (

        100
        * deadline_misses
        / len(all_jobs)
    )


    summary = {

        "scheduler": policy,

        "total_jobs":
            len(all_jobs),

        "completed_jobs":
            len(finished_jobs),

        "deadline_misses":
            deadline_misses,

        "deadline_miss_ratio_percent":
            round(
                deadline_miss_ratio,
                3
            ),

        "average_response_time_ms":
            round(
                sum(response_times)
                / len(response_times),
                3
            ),

        "maximum_response_time_ms":
            max(response_times),

        "maximum_tardiness_ms":
            max(tardiness),

        "preemptions":
            preemptions,

        "recovery_time_ms":
            recovery_time
    }


    return (
        summary,
        all_jobs,
        timeline,
        cumulative_misses
    )


# ==========================================================
# 6. SAVE RESULTS TO CSV
# ==========================================================

def save_results(results):

    os.makedirs(
        "results",
        exist_ok=True
    )


    # ------------------------------------------------------
    # Summary CSV
    # ------------------------------------------------------

    with open(
        "results/summary.csv",
        "w",
        newline=""
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=results[0][0].keys()
        )

        writer.writeheader()

        for summary, _, _, _ in results:

            writer.writerow(summary)


    # ------------------------------------------------------
    # Individual job results
    # ------------------------------------------------------

    with open(
        "results/job_results.csv",
        "w",
        newline=""
    ) as file:

        fields = [

            "scheduler",
            "job_id",
            "task",
            "criticality",
            "release_ms",
            "deadline_ms",
            "completed_at_ms",
            "response_time_ms",
            "missed_deadline"
        ]


        writer = csv.DictWriter(
            file,
            fieldnames=fields
        )

        writer.writeheader()


        for (
            summary,
            jobs,
            _,
            _
        ) in results:

            scheduler = summary[
                "scheduler"
            ]


            for job in jobs:

                if job.completed_at is None:

                    response_time = None

                else:

                    response_time = (
                        job.completed_at
                        - job.release
                    )


                writer.writerow({

                    "scheduler":
                        scheduler,

                    "job_id":
                        job.uid,

                    "task":
                        job.task.name,

                    "criticality":
                        job.task.criticality,

                    "release_ms":
                        job.release,

                    "deadline_ms":
                        job.deadline,

                    "completed_at_ms":
                        job.completed_at,

                    "response_time_ms":
                        response_time,

                    "missed_deadline":
                        job.missed
                })


# ==========================================================
# 7. CREATE GRAPHS
# ==========================================================

def make_plots(results):

    os.makedirs(
        "results",
        exist_ok=True
    )


    schedulers = [

        result[0]["scheduler"]

        for result in results
    ]


    deadline_misses = [

        result[0]["deadline_misses"]

        for result in results
    ]


    recovery_times = [

        result[0]["recovery_time_ms"]

        for result in results
    ]


    # ------------------------------------------------------
    # Graph 1: Total deadline misses
    # ------------------------------------------------------

    plt.figure(
        figsize=(7, 4)
    )

    plt.bar(
        schedulers,
        deadline_misses
    )

    plt.ylabel(
        "Number of Deadline Misses"
    )

    plt.xlabel(
        "Scheduling Algorithm"
    )

    plt.title(
        "EDF vs RMS Deadline Misses"
    )

    plt.tight_layout()

    plt.savefig(
        "results/deadline_misses.png",
        dpi=200
    )

    plt.close()


    # ------------------------------------------------------
    # Graph 2: Cumulative deadline misses over time
    # ------------------------------------------------------

    plt.figure(
        figsize=(8, 5)
    )


    for (
        summary,
        _,
        _,
        cumulative
    ) in results:

        time_values = [

            point[0]

            for point in cumulative
        ]


        miss_values = [

            point[1]

            for point in cumulative
        ]


        plt.plot(

            time_values,

            miss_values,

            label=summary[
                "scheduler"
            ]
        )


    # Highlight overload period
    plt.axvspan(

        OVERLOAD_START,

        OVERLOAD_END,

        alpha=0.15,

        label="Transient overload"
    )


    plt.xlabel(
        "Simulation Time (ms)"
    )

    plt.ylabel(
        "Cumulative Deadline Misses"
    )

    plt.title(
        "Deadline Misses During Transient Overload"
    )

    plt.legend()

    plt.tight_layout()

    plt.savefig(
        "results/cumulative_deadline_misses.png",
        dpi=200
    )

    plt.close()


    # ------------------------------------------------------
    # Graph 3: Recovery time
    # ------------------------------------------------------

    plt.figure(
        figsize=(7, 4)
    )

    plt.bar(
        schedulers,
        recovery_times
    )

    plt.ylabel(
        "Recovery Time (ms)"
    )

    plt.xlabel(
        "Scheduling Algorithm"
    )

    plt.title(
        "Recovery After Transient Overload"
    )

    plt.tight_layout()

    plt.savefig(
        "results/recovery_time.png",
        dpi=200
    )

    plt.close()


# ==========================================================
# 8. PRINT DEADLINE MISSES PER TASK
# ==========================================================

def print_task_misses(
    scheduler,
    jobs
):

    print(
        f"\n{scheduler} misses by task"
    )

    task_names = sorted(

        set(
            job.task.name

            for job in jobs
        )
    )


    for task_name in task_names:

        misses = sum(

            1

            for job in jobs

            if (
                job.task.name
                == task_name

                and job.missed
            )
        )


        print(
            f"{task_name:12s}: {misses}"
        )


# ==========================================================
# 9. MAIN PROGRAM
# ==========================================================

def main():

    normal_utilisation = utilisation(
        NORMAL_TASKS
    )


    overload_utilisation = (

        OVERLOAD_TASK.wcet

        / OVERLOAD_TASK.period
    )


    print(
        "\nAUTOMOTIVE RTOS SCHEDULING SIMULATION"
    )

    print(
        "====================================="
    )


    print(
        f"\nNormal CPU utilisation: "
        f"{normal_utilisation * 100:.1f}%"
    )


    print(
        f"CPU utilisation during overload: "
        f"{(normal_utilisation + overload_utilisation) * 100:.1f}%"
    )


    results = []


    # Run exactly the same workload
    # using RMS and EDF

    for scheduler in [
        "RMS",
        "EDF"
    ]:

        result = simulate(
            scheduler
        )

        results.append(
            result
        )


        summary, jobs, _, _ = result


        print(
            f"\n---------------- {scheduler} ----------------"
        )


        for key, value in summary.items():

            print(
                f"{key}: {value}"
            )


        print_task_misses(
            scheduler,
            jobs
        )


    # Save CSV
    save_results(
        results
    )


    # Produce graphs
    make_plots(
        results
    )


    print(
        "\nSimulation finished."
    )

    print(
        "Open the 'results' folder "
        "to see CSV files and graphs."
    )


# ==========================================================
# START PROGRAM
# ==========================================================

if __name__ == "__main__":

    main()