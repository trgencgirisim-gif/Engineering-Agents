# Shared Anthropic model pricing — single source of truth
# Rates are per-token (divide $/M by 1_000_000)


def get_rates(model: str):
    """
    Returns (r_in, r_out, r_cre, r_rd) pricing rates for the given model.

    r_in  — normal input token rate
    r_out — output token rate
    r_cre — cache creation rate (+25% of input)
    r_rd  — cache read rate (-90% of input)
    """
    if "opus" in model:
        return 15 / 1_000_000, 75 / 1_000_000, 18.75 / 1_000_000, 1.5 / 1_000_000
    elif "sonnet" in model:
        return 3 / 1_000_000, 15 / 1_000_000, 3.75 / 1_000_000, 0.3 / 1_000_000
    else:  # haiku / fallback
        return 0.8 / 1_000_000, 4 / 1_000_000, 1.0 / 1_000_000, 0.08 / 1_000_000


def compute_cost(model: str, inp: int, out: int, c_cre: int = 0, c_rd: int = 0):
    """
    Compute actual cost and cache savings for an API call.

    Returns (actual_cost, saved) in USD.
    """
    r_in, r_out, r_cre, r_rd = get_rates(model)
    actual_cost = (inp * r_in) + (out * r_out) + (c_cre * r_cre) + (c_rd * r_rd)
    full_cost = ((inp + c_cre + c_rd) * r_in) + (out * r_out)
    saved = max(0.0, full_cost - actual_cost)
    return actual_cost, saved
