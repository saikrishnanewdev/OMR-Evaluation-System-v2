"""Competition ranking algorithm (1224) and tie-breaking policies."""
from typing import List, Dict
from app.models.entities import ProcessedSheet


class RankingEngine:
    """Computes standard competition ranks with deterministic secondary ordering."""

    @classmethod
    def compute_ranks(cls, sheets: List[ProcessedSheet]) -> Dict[int, int]:
        """
        Calculates competition ranks (1, 2, 2, 4...) for a list of processed sheets.
        Returns a mapping from sheet.id to rank integer.
        """
        if not sheets:
            return {}

        # Filter out rejected sheets from ranking
        rankable_sheets = [s for s in sheets if s.status != "REJECTED" and s.id is not None]

        # Deterministic sorting:
        # 1. Total marks (descending)
        # 2. Correct count (descending)
        # 3. Wrong count (ascending)
        # 4. Display identifier (ascending)
        sorted_sheets = sorted(
            rankable_sheets,
            key=lambda s: (
                -s.total_marks,
                -s.correct_count,
                s.wrong_count,
                s.display_identifier
            )
        )

        ranks: Dict[int, int] = {}
        curr_rank = 1
        i = 0
        n = len(sorted_sheets)

        while i < n:
            curr_sheet = sorted_sheets[i]
            # Find all subsequent sheets with identical total_marks
            tied_sheets = [curr_sheet]
            j = i + 1
            while j < n and sorted_sheets[j].total_marks == curr_sheet.total_marks:
                tied_sheets.append(sorted_sheets[j])
                j += 1

            # Assign same rank to all tied candidates
            for sheet in tied_sheets:
                ranks[sheet.id] = curr_rank
                sheet.student_rank = curr_rank

            # In competition ranking (1224), next rank skips by number of tied entries
            curr_rank += len(tied_sheets)
            i = j

        return ranks

