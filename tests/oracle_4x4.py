"""Small backtracking oracle: no SAT, mapping, checker or generator imports."""


def solutions_4x4(grid, limit=2):
    """Find up to limit solutions, only for the fixed 4x4 test domain."""
    if type(limit) is not int or limit < 1:
        raise ValueError("positive integer limit required")
    if not isinstance(grid, (list, tuple)) or len(grid) != 4:
        raise ValueError("oracle requires a 4x4 grid")
    if any(not isinstance(row, (list, tuple)) or len(row) != 4 for row in grid):
        raise ValueError("oracle requires four cells per row")
    if any(type(v) is not int or not 0 <= v <= 4 for row in grid for v in row):
        raise ValueError("oracle values must be exact ints in 0..4")
    board = [list(row) for row in grid]

    def allowed(r, c, value):
        for j in range(4):
            if j != c and board[r][j] == value:
                return False
        for i in range(4):
            if i != r and board[i][c] == value:
                return False
        br, bc = (r // 2) * 2, (c // 2) * 2
        for i in range(br, br + 2):
            for j in range(bc, bc + 2):
                if (i, j) != (r, c) and board[i][j] == value:
                    return False
        return True

    if any(board[r][c] and not allowed(r, c, board[r][c])
           for r in range(4) for c in range(4)):
        return []
    found = []

    def search():
        if len(found) >= limit:
            return
        empty = next(((r, c) for r in range(4) for c in range(4) if not board[r][c]), None)
        if empty is None:
            found.append(tuple(tuple(row) for row in board))
            return
        r, c = empty
        for value in range(1, 5):
            if allowed(r, c, value):
                board[r][c] = value
                search()
                board[r][c] = 0
                if len(found) >= limit:
                    break

    search()
    return found
