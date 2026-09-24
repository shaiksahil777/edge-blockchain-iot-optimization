
import random
import math
import hashlib
import csv
from statistics import mean, stdev
from pathlib import Path
import matplotlib.pyplot as plt

# ============================================================
# FINAL VALIDATION: IoT + EDGE + BLOCKCHAIN + PSO + WOA
# ============================================================

NUM_IOT_DEVICES = 15
NUM_EDGE_NODES = 3
NUM_VALIDATORS = 3
MALICIOUS_RATE = 0.10

NUM_RUNS = 5
RUN_SEEDS = [42, 123, 456, 789, 1024]

# Baseline
BASELINE = {
    "block_size": 5,
    "timeout": 0.075,       # seconds; now acts as a real consensus deadline
    "cpu": 50.0,
    "memory": 50.0,
    "bandwidth": 50.0,
}

# Search bounds
BOUNDS = {
    "block_size": (2, 10),
    "timeout": (0.045, 0.100),
    "cpu": (20.0, 100.0),
    "memory": (20.0, 100.0),
    "bandwidth": (20.0, 100.0),
}

POPULATION_SIZE = 10
ITERATIONS = 15

# Multi-objective fitness weights
W_LATENCY = 0.30
W_ENERGY = 0.25
W_THROUGHPUT = 0.20
W_SECURITY_ERROR = 0.15
W_RESOURCE = 0.10

# Total allocation budget across the three resource dimensions.
# Prevents the optimizer from simply choosing 100% for everything.
MAX_RESOURCE_SUM = 210.0

OUTPUT_DIR = Path("final_validation_results")
OUTPUT_DIR.mkdir(exist_ok=True)


# ============================================================
# 1. IoT DEVICE
# ============================================================

class IoTDevice:
    def __init__(self, device_id):
        self.device_id = device_id

    def generate_data(self, rng, malicious=False):
        if malicious:
            # Synthetic attack: impossible temperature value.
            temperature = rng.choice([
                rng.uniform(-40, 0),
                rng.uniform(80, 120)
            ])
        else:
            temperature = rng.uniform(20, 40)

        return {
            "device_id": self.device_id,
            "temperature": temperature,
            "message_size": rng.uniform(1, 5),
            "malicious": malicious,
        }


# ============================================================
# 2. EDGE NODE
# ============================================================

class EdgeNode:
    def __init__(self, node_id):
        self.node_id = node_id
        self.max_cpu = 100.0
        self.max_memory = 100.0
        self.max_bandwidth = 100.0

    def process(self, transaction, configuration, rng):
        cpu = configuration["cpu"]
        memory = configuration["memory"]
        bandwidth = configuration["bandwidth"]

        # Resource allocation affects processing and communication.
        processing_delay = rng.uniform(0.010, 0.030) * (100.0 / cpu)
        memory_factor = 1.0 + max(0.0, 50.0 - memory) / 200.0
        processing_delay *= memory_factor

        network_delay = rng.uniform(0.010, 0.040) * (
            100.0 / bandwidth
        )

        return processing_delay, network_delay


# ============================================================
# 3. LIGHTWEIGHT BLOCKCHAIN
# ============================================================

class Blockchain:
    def __init__(self):
        self.chain = []

    def add_block(self, transactions):
        previous_hash = "0" if not self.chain else self.chain[-1]["hash"]

        block = {
            "block_number": len(self.chain) + 1,
            "transactions": transactions,
            "previous_hash": previous_hash,
        }

        block["hash"] = hashlib.sha256(
            str(block).encode("utf-8")
        ).hexdigest()

        self.chain.append(block)

    def is_valid(self):
        previous_hash = "0"

        for block in self.chain:
            if block["previous_hash"] != previous_hash:
                return False

            block_without_hash = {
                "block_number": block["block_number"],
                "transactions": block["transactions"],
                "previous_hash": block["previous_hash"],
            }

            expected_hash = hashlib.sha256(
                str(block_without_hash).encode("utf-8")
            ).hexdigest()

            if block["hash"] != expected_hash:
                return False

            previous_hash = block["hash"]

        return True


# ============================================================
# 4. VALIDATOR / CONSENSUS
# ============================================================

class Validator:
    def __init__(self, validator_id):
        self.validator_id = validator_id

    def validate(self, transaction):
        # Synthetic security rule:
        # normal IoT temperature must be in [20, 40].
        return 20.0 <= transaction["temperature"] <= 40.0


def majority_consensus(transaction, validators):
    votes = sum(
        validator.validate(transaction)
        for validator in validators
    )
    return votes > len(validators) / 2


# ============================================================
# 5. SIMULATION
# ============================================================

def run_simulation(configuration, seed=42):
    rng = random.Random(seed)

    devices = [
        IoTDevice(i + 1) for i in range(NUM_IOT_DEVICES)
    ]
    edge_nodes = [
        EdgeNode(i + 1) for i in range(NUM_EDGE_NODES)
    ]
    validators = [
        Validator(i + 1) for i in range(NUM_VALIDATORS)
    ]

    blockchain = Blockchain()

    total_latency = 0.0
    total_energy = 0.0
    total_consensus_time = 0.0

    successful_transactions = 0
    total_transactions = 0

    malicious_total = 0
    malicious_detected = 0
    malicious_accepted = 0
    legitimate_accepted = 0

    accepted_transactions = []

    # --------------------------------------------------------
    # IoT traffic generation
    # --------------------------------------------------------

    transactions = []

    for device in devices:
        is_malicious = rng.random() < MALICIOUS_RATE

        if is_malicious:
            malicious_total += 1

        transactions.append(
            device.generate_data(
                rng,
                malicious=is_malicious
            )
        )

    # --------------------------------------------------------
    # IoT -> Edge -> Validator / Consensus
    # --------------------------------------------------------

    for index, transaction in enumerate(transactions):
        total_transactions += 1

        edge = edge_nodes[index % NUM_EDGE_NODES]

        processing_delay, network_delay = edge.process(
            transaction,
            configuration,
            rng
        )

        block_size = int(round(configuration["block_size"]))

        # Larger blocks require slightly more consensus work.
        block_delay = 0.020 + (block_size * 0.0040)

        # Validator processing.
        validator_delay = rng.uniform(0.020, 0.040)

        raw_consensus_time = (
            block_delay + validator_delay
        )

        # Timeout is a real acceptance condition.
        consensus_accepted = (
            raw_consensus_time <= configuration["timeout"]
        )

        if consensus_accepted:
            consensus_time = raw_consensus_time
        else:
            # Failed consensus waits until the configured deadline.
            consensus_time = configuration["timeout"]

        latency = (
            network_delay
            + processing_delay
            + consensus_time
        )

        energy = (
            processing_delay * 5.0
            + network_delay * 3.0
            + consensus_time * 4.0
        )

        total_latency += latency
        total_energy += energy
        total_consensus_time += consensus_time

        security_decision = majority_consensus(
            transaction,
            validators
        )

        if transaction["malicious"]:
            if not security_decision:
                malicious_detected += 1
            else:
                malicious_accepted += 1
        else:
            if security_decision and consensus_accepted:
                legitimate_accepted += 1

        if security_decision and consensus_accepted:
            successful_transactions += 1
            accepted_transactions.append(transaction)

    # --------------------------------------------------------
    # Blockchain stores only accepted transactions.
    # --------------------------------------------------------

    block_size = int(round(configuration["block_size"]))

    for i in range(
        0,
        len(accepted_transactions),
        block_size
    ):
        blockchain.add_block(
            accepted_transactions[i:i + block_size]
        )

    # --------------------------------------------------------
    # Metrics
    # --------------------------------------------------------

    average_latency = total_latency / total_transactions
    average_energy = total_energy / total_transactions
    average_consensus = (
        total_consensus_time / total_transactions
    )

    throughput = (
        successful_transactions / total_latency
        if total_latency > 0 else 0.0
    )

    # Actual configured resource allocation.
    average_allocation = (
        configuration["cpu"]
        + configuration["memory"]
        + configuration["bandwidth"]
    ) / 3.0

    # Security detection rate: malicious transactions detected.
    security_detection_rate = (
        malicious_detected / malicious_total
        if malicious_total > 0 else 1.0
    )

    security_error = 1.0 - security_detection_rate

    return {
        "latency": average_latency,
        "energy": average_energy,
        "throughput": throughput,
        "consensus_time": average_consensus,
        "resource_utilization": average_allocation,
        "security_detection_rate": security_detection_rate,
        "security_error": security_error,
        "successful_transactions": successful_transactions,
        "total_transactions": total_transactions,
        "malicious_total": malicious_total,
        "malicious_detected": malicious_detected,
        "malicious_accepted": malicious_accepted,
        "legitimate_accepted": legitimate_accepted,
        "blocks": len(blockchain.chain),
        "blockchain_integrity": blockchain.is_valid(),
    }


# ============================================================
# 6. NORMALIZATION + FITNESS
# ============================================================

def make_fitness_function(baseline_results, evaluation_seed):
    baseline_latency = max(baseline_results["latency"], 1e-12)
    baseline_energy = max(baseline_results["energy"], 1e-12)
    baseline_throughput = max(
        baseline_results["throughput"], 1e-12
    )

    def fitness(configuration):
        results = run_simulation(
            configuration,
            seed=evaluation_seed
        )

        latency_score = (
            results["latency"] / baseline_latency
        )

        energy_score = (
            results["energy"] / baseline_energy
        )

        throughput_score = (
            baseline_throughput
            / max(results["throughput"], 1e-12)
        )

        security_error = results["security_error"]

        # Prefer allocations near a balanced target of 70%.
        resource_balance = (
            abs(results["resource_utilization"] - 70.0)
            / 70.0
        )

        score = (
            W_LATENCY * latency_score
            + W_ENERGY * energy_score
            + W_THROUGHPUT * throughput_score
            + W_SECURITY_ERROR * security_error
            + W_RESOURCE * resource_balance
        )

        # Hard resource-budget constraint.
        resource_sum = (
            configuration["cpu"]
            + configuration["memory"]
            + configuration["bandwidth"]
        )

        if resource_sum > MAX_RESOURCE_SUM:
            score += (
                (resource_sum - MAX_RESOURCE_SUM) / 100.0
            )

        return score, results

    return fitness


# ============================================================
# 7. SOLUTION HELPERS
# ============================================================

PARAMETERS = [
    "block_size",
    "timeout",
    "cpu",
    "memory",
    "bandwidth",
]


def create_solution(rng):
    return {
        "block_size": rng.randint(
            BOUNDS["block_size"][0],
            BOUNDS["block_size"][1]
        ),
        "timeout": rng.uniform(
            *BOUNDS["timeout"]
        ),
        "cpu": rng.uniform(
            *BOUNDS["cpu"]
        ),
        "memory": rng.uniform(
            *BOUNDS["memory"]
        ),
        "bandwidth": rng.uniform(
            *BOUNDS["bandwidth"]
        ),
    }


def clamp_solution(solution):
    solution["block_size"] = int(
        max(
            BOUNDS["block_size"][0],
            min(
                BOUNDS["block_size"][1],
                round(solution["block_size"])
            )
        )
    )

    for parameter in [
        "timeout",
        "cpu",
        "memory",
        "bandwidth",
    ]:
        low, high = BOUNDS[parameter]
        solution[parameter] = max(
            low,
            min(high, solution[parameter])
        )

    # Repair resource budget while preserving minimum values.
    total = (
        solution["cpu"]
        + solution["memory"]
        + solution["bandwidth"]
    )

    if total > MAX_RESOURCE_SUM:
        scale = MAX_RESOURCE_SUM / total
        for parameter in [
            "cpu",
            "memory",
            "bandwidth",
        ]:
            low, _ = BOUNDS[parameter]
            solution[parameter] = max(
                low,
                solution[parameter] * scale
            )

    return solution


# ============================================================
# 8. PSO
# ============================================================

def run_pso(fitness, optimizer_seed):
    rng = random.Random(optimizer_seed)

    particles = []
    velocities = []
    personal_best = []
    personal_best_score = []

    for _ in range(POPULATION_SIZE):
        particle = create_solution(rng)

        velocity = {
            parameter: 0.0
            for parameter in PARAMETERS
        }

        score, _ = fitness(particle)

        particles.append(particle)
        velocities.append(velocity)
        personal_best.append(particle.copy())
        personal_best_score.append(score)

    best_index = personal_best_score.index(
        min(personal_best_score)
    )

    global_best = personal_best[best_index].copy()
    global_best_score = personal_best_score[best_index]

    w = 0.7
    c1 = 1.5
    c2 = 1.5

    convergence = []

    for _ in range(ITERATIONS):
        for i in range(POPULATION_SIZE):
            particle = particles[i]
            velocity = velocities[i]

            for parameter in PARAMETERS:
                r1 = rng.random()
                r2 = rng.random()

                velocity[parameter] = (
                    w * velocity[parameter]
                    + c1 * r1 * (
                        personal_best[i][parameter]
                        - particle[parameter]
                    )
                    + c2 * r2 * (
                        global_best[parameter]
                        - particle[parameter]
                    )
                )

                particle[parameter] += velocity[parameter]

            clamp_solution(particle)

            score, _ = fitness(particle)

            if score < personal_best_score[i]:
                personal_best[i] = particle.copy()
                personal_best_score[i] = score

            if score < global_best_score:
                global_best = particle.copy()
                global_best_score = score

        convergence.append(global_best_score)

    return (
        global_best,
        global_best_score,
        convergence
    )


# ============================================================
# 9. WOA
# ============================================================

def run_woa(fitness, optimizer_seed):
    rng = random.Random(optimizer_seed)

    whales = []
    whale_scores = []

    for _ in range(POPULATION_SIZE):
        whale = create_solution(rng)
        score, _ = fitness(whale)

        whales.append(whale)
        whale_scores.append(score)

    best_index = whale_scores.index(
        min(whale_scores)
    )

    best_whale = whales[best_index].copy()
    best_score = whale_scores[best_index]

    convergence = []

    for iteration in range(ITERATIONS):
        a = 2.0 - (
            2.0 * iteration / ITERATIONS
        )

        for i in range(POPULATION_SIZE):
            whale = whales[i]

            r1 = rng.random()
            r2 = rng.random()

            A = 2.0 * a * r1 - a
            C = 2.0 * r2
            p = rng.random()

            if p < 0.5:
                for parameter in PARAMETERS:
                    distance = abs(
                        C * best_whale[parameter]
                        - whale[parameter]
                    )

                    whale[parameter] = (
                        best_whale[parameter]
                        - A * distance
                    )

            else:
                l = rng.uniform(-1.0, 1.0)

                for parameter in PARAMETERS:
                    distance = abs(
                        best_whale[parameter]
                        - whale[parameter]
                    )

                    whale[parameter] = (
                        distance
                        * math.exp(l)
                        * math.cos(2.0 * math.pi * l)
                        + best_whale[parameter]
                    )

            clamp_solution(whale)

            score, _ = fitness(whale)
            whale_scores[i] = score

            if score < best_score:
                best_whale = whale.copy()
                best_score = score

        convergence.append(best_score)

    return (
        best_whale,
        best_score,
        convergence
    )


# ============================================================
# 10. EXPERIMENT
# ============================================================

all_results = {
    "Baseline": [],
    "PSO": [],
    "WOA": [],
}

all_pso_convergence = []
all_woa_convergence = []

pso_configs = []
woa_configs = []

print("\n" + "=" * 80)
print("FINAL VALIDATION: IoT + EDGE + BLOCKCHAIN + PSO + WOA")
print("=" * 80)
print(f"IoT devices        : {NUM_IOT_DEVICES}")
print(f"Edge nodes         : {NUM_EDGE_NODES}")
print(f"Validators         : {NUM_VALIDATORS}")
print(f"Malicious traffic  : {MALICIOUS_RATE * 100:.1f}%")
print(f"Independent runs   : {NUM_RUNS}")
print(f"PSO/WOA population : {POPULATION_SIZE}")
print(f"PSO/WOA iterations : {ITERATIONS}")
print("=" * 80)

for run_number, seed in enumerate(RUN_SEEDS, start=1):
    print(
        f"\nRUN {run_number}/{NUM_RUNS} | SEED = {seed}"
    )

    baseline_results = run_simulation(
        BASELINE,
        seed=seed
    )

    fitness = make_fitness_function(
        baseline_results,
        evaluation_seed=seed
    )

    pso_config, pso_score, pso_convergence = run_pso(
        fitness,
        optimizer_seed=seed + 1000
    )

    woa_config, woa_score, woa_convergence = run_woa(
        fitness,
        optimizer_seed=seed + 2000
    )

    pso_results = run_simulation(
        pso_config,
        seed=seed
    )

    woa_results = run_simulation(
        woa_config,
        seed=seed
    )

    all_results["Baseline"].append(baseline_results)
    all_results["PSO"].append(pso_results)
    all_results["WOA"].append(woa_results)

    all_pso_convergence.append(pso_convergence)
    all_woa_convergence.append(woa_convergence)

    pso_configs.append(pso_config)
    woa_configs.append(woa_config)

    print(
        f"Baseline: latency={baseline_results['latency']:.5f}, "
        f"security={baseline_results['security_detection_rate']:.2%}, "
        f"integrity={baseline_results['blockchain_integrity']}"
    )
    print(
        f"PSO     : latency={pso_results['latency']:.5f}, "
        f"security={pso_results['security_detection_rate']:.2%}, "
        f"integrity={pso_results['blockchain_integrity']}"
    )
    print(
        f"WOA     : latency={woa_results['latency']:.5f}, "
        f"security={woa_results['security_detection_rate']:.2%}, "
        f"integrity={woa_results['blockchain_integrity']}"
    )


# ============================================================
# 11. SUMMARY
# ============================================================

METRICS = [
    ("latency", "Latency (sec)", "lower"),
    ("energy", "Energy / transaction", "lower"),
    ("throughput", "Throughput (tx/sec)", "higher"),
    ("consensus_time", "Consensus time (sec)", "lower"),
    ("resource_utilization", "Resource allocation (%)", "target"),
    ("security_detection_rate", "Security detection rate (%)", "higher"),
]

summary = {}

print("\n" + "=" * 100)
print("5-RUN AVERAGE RESULTS (mean ± standard deviation)")
print("=" * 100)
print(
    f"{'Metric':<30}"
    f"{'Baseline':<22}"
    f"{'PSO':<22}"
    f"{'WOA':<22}"
)
print("-" * 100)

for metric, label, direction in METRICS:
    values = {}

    for method in ["Baseline", "PSO", "WOA"]:
        data = [
            result[metric]
            for result in all_results[method]
        ]

        values[method] = {
            "mean": mean(data),
            "std": stdev(data) if len(data) > 1 else 0.0,
        }

    summary[metric] = values

    if "rate" in metric:
        fmt = lambda x: f"{x * 100:.2f}%"
    else:
        fmt = lambda x: f"{x:.5f}"

    print(
        f"{label:<30}"
        f"{fmt(values['Baseline']['mean'])} ± {fmt(values['Baseline']['std']):<10}"
        f"{fmt(values['PSO']['mean'])} ± {fmt(values['PSO']['std']):<10}"
        f"{fmt(values['WOA']['mean'])} ± {fmt(values['WOA']['std']):<10}"
    )


# ============================================================
# 12. SECURITY VALIDATION
# ============================================================

print("\n" + "=" * 100)
print("SECURITY VALIDATION")
print("=" * 100)

for method in ["Baseline", "PSO", "WOA"]:
    malicious_total = sum(
        r["malicious_total"]
        for r in all_results[method]
    )
    malicious_detected = sum(
        r["malicious_detected"]
        for r in all_results[method]
    )
    malicious_accepted = sum(
        r["malicious_accepted"]
        for r in all_results[method]
    )

    detection_rate = (
        malicious_detected / malicious_total
        if malicious_total else 1.0
    )

    print(f"\n{method}")
    print(f"  Malicious transactions : {malicious_total}")
    print(f"  Detected               : {malicious_detected}")
    print(f"  Malicious accepted     : {malicious_accepted}")
    print(f"  Detection rate         : {detection_rate:.2%}")


# ============================================================
# 13. BLOCKCHAIN INTEGRITY
# ============================================================

print("\n" + "=" * 100)
print("BLOCKCHAIN INTEGRITY")
print("=" * 100)

for method in ["Baseline", "PSO", "WOA"]:
    integrity = all(
        result["blockchain_integrity"]
        for result in all_results[method]
    )

    average_blocks = mean(
        result["blocks"]
        for result in all_results[method]
    )

    print(
        f"{method:<10} | "
        f"All runs valid: {integrity} | "
        f"Average blocks: {average_blocks:.2f}"
    )


# ============================================================
# 14. IMPROVEMENT
# ============================================================

print("\n" + "=" * 100)
print("IMPROVEMENT OVER BASELINE")
print("=" * 100)

for metric, label, direction in METRICS:
    baseline = summary[metric]["Baseline"]["mean"]
    pso = summary[metric]["PSO"]["mean"]
    woa = summary[metric]["WOA"]["mean"]

    if direction == "lower":
        pso_imp = (baseline - pso) / baseline * 100
        woa_imp = (baseline - woa) / baseline * 100
    elif direction == "higher":
        pso_imp = (pso - baseline) / baseline * 100
        woa_imp = (woa - baseline) / baseline * 100
    else:
        # Resource allocation is a diagnostic/target metric,
        # not a simple "higher is better" metric.
        pso_imp = None
        woa_imp = None

    print(f"\n{label}")

    if pso_imp is None:
        print("  Diagnostic metric: compare allocation balance.")
    else:
        print(f"  PSO: {pso_imp:+.2f}%")
        print(f"  WOA: {woa_imp:+.2f}%")


# ============================================================
# 15. OPTIMIZED PARAMETERS
# ============================================================

def average_config(configs):
    return {
        parameter: mean(
            config[parameter]
            for config in configs
        )
        for parameter in PARAMETERS
    }


avg_pso_config = average_config(pso_configs)
avg_woa_config = average_config(woa_configs)

print("\n" + "=" * 100)
print("AVERAGE OPTIMIZED PARAMETERS")
print("=" * 100)

for parameter in PARAMETERS:
    print(
        f"{parameter:<12} | "
        f"Baseline={BASELINE[parameter]:.3f} | "
        f"PSO={avg_pso_config[parameter]:.3f} | "
        f"WOA={avg_woa_config[parameter]:.3f}"
    )


# ============================================================
# 16. CONVERGENCE
# ============================================================

avg_pso_convergence = [
    mean(values[i] for values in all_pso_convergence)
    for i in range(ITERATIONS)
]

avg_woa_convergence = [
    mean(values[i] for values in all_woa_convergence)
    for i in range(ITERATIONS)
]

plt.figure(figsize=(8, 5))
plt.plot(
    range(1, ITERATIONS + 1),
    avg_pso_convergence,
    marker="o",
    label="PSO"
)
plt.plot(
    range(1, ITERATIONS + 1),
    avg_woa_convergence,
    marker="s",
    label="WOA"
)
plt.xlabel("Iteration")
plt.ylabel("Best Fitness")
plt.title("PSO vs WOA Convergence")
plt.grid(True, alpha=0.3)
plt.legend()
plt.tight_layout()
plt.savefig(
    OUTPUT_DIR / "convergence_pso_woa.png",
    dpi=200
)
plt.close()


# ============================================================
# 17. METRIC COMPARISON GRAPHS
# ============================================================

for metric, label, direction in METRICS:
    baseline = summary[metric]["Baseline"]["mean"]
    pso = summary[metric]["PSO"]["mean"]
    woa = summary[metric]["WOA"]["mean"]

    values = [baseline, pso, woa]

    if "rate" in metric:
        values = [v * 100 for v in values]
        ylabel = "Percentage (%)"
    elif metric == "throughput":
        ylabel = "Transactions / second"
    elif metric == "resource_utilization":
        ylabel = "Allocation (%)"
    elif metric == "energy":
        ylabel = "Energy / transaction"
    else:
        ylabel = "Seconds"

    plt.figure(figsize=(7, 5))
    plt.bar(
        ["Baseline", "PSO", "WOA"],
        values
    )
    plt.ylabel(ylabel)
    plt.title(label + " Comparison")
    plt.tight_layout()

    safe_name = metric.replace(
        "_",
        "-"
    )

    plt.savefig(
        OUTPUT_DIR / f"{safe_name}_comparison.png",
        dpi=200
    )
    plt.close()


# ============================================================
# 18. SAVE RUN-LEVEL CSV
# ============================================================

run_csv = OUTPUT_DIR / "run_level_results.csv"

with open(run_csv, "w", newline="") as file:
    writer = csv.writer(file)

    writer.writerow([
        "Run",
        "Seed",
        "Method",
        "Latency",
        "Energy",
        "Throughput",
        "Consensus_Time",
        "Resource_Utilization",
        "Security_Detection_Rate",
        "Malicious_Total",
        "Malicious_Detected",
        "Malicious_Accepted",
        "Legitimate_Accepted",
        "Successful_Transactions",
        "Blocks",
        "Blockchain_Integrity",
    ])

    for run_index, seed in enumerate(
        RUN_SEEDS,
        start=1
    ):
        for method in ["Baseline", "PSO", "WOA"]:
            r = all_results[method][run_index - 1]

            writer.writerow([
                run_index,
                seed,
                method,
                r["latency"],
                r["energy"],
                r["throughput"],
                r["consensus_time"],
                r["resource_utilization"],
                r["security_detection_rate"],
                r["malicious_total"],
                r["malicious_detected"],
                r["malicious_accepted"],
                r["legitimate_accepted"],
                r["successful_transactions"],
                r["blocks"],
                r["blockchain_integrity"],
            ])


# ============================================================
# 19. SAVE SUMMARY CSV
# ============================================================

summary_csv = OUTPUT_DIR / "summary_results.csv"

with open(summary_csv, "w", newline="") as file:
    writer = csv.writer(file)

    writer.writerow([
        "Metric",
        "Baseline_Mean",
        "Baseline_STD",
        "PSO_Mean",
        "PSO_STD",
        "WOA_Mean",
        "WOA_STD",
    ])

    for metric, label, _ in METRICS:
        writer.writerow([
            label,
            summary[metric]["Baseline"]["mean"],
            summary[metric]["Baseline"]["std"],
            summary[metric]["PSO"]["mean"],
            summary[metric]["PSO"]["std"],
            summary[metric]["WOA"]["mean"],
            summary[metric]["WOA"]["std"],
        ])


# ============================================================
# 20. FINAL STATUS
# ============================================================

all_integrity_valid = all(
    result["blockchain_integrity"]
    for method_results in all_results.values()
    for result in method_results
)

all_security_runs_valid = all(
    result["malicious_accepted"] == 0
    for method_results in all_results.values()
    for result in method_results
)

print("\n" + "=" * 100)
print("FINAL VALIDATION STATUS")
print("=" * 100)
print(f"Blockchain integrity across all runs : {all_integrity_valid}")
print(
    f"No malicious transaction accepted   : "
    f"{all_security_runs_valid}"
)
print(
    f"Convergence graph saved              : "
    f"{OUTPUT_DIR / 'convergence_pso_woa.png'}"
)
print(
    f"Run-level CSV saved                  : "
    f"{run_csv}"
)
print(
    f"Summary CSV saved                    : "
    f"{summary_csv}"
)
print("=" * 100)
print("Simulation completed successfully.")
