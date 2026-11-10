"""Minimal, dependency-light ML primitives (numpy + scipy).

scikit-learn's compiled extensions are blocked by Windows Smart App Control on
the development machine, and a lender's on-prem stack may restrict them too
so the few primitives Saakh needs are implemented here, small and auditable.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize
from scipy.stats import rankdata


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -35, 35)))


class LogReg:
    """L2-regularised logistic regression (intercept not penalised), L-BFGS."""

    def __init__(self, C: float = 1.0):
        self.C = C
        self.coef_ = None
        self.intercept_ = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray):
        X = np.asarray(X, float)
        y = np.asarray(y, float)
        n, k = X.shape
        lam = 1.0 / self.C

        def f(w):
            z = X @ w[1:] + w[0]
            # stable log-loss
            loss = np.sum(np.logaddexp(0, z) - y * z) + 0.5 * lam * np.dot(w[1:], w[1:])
            p = sigmoid(z)
            g0 = np.sum(p - y)
            g = X.T @ (p - y) + lam * w[1:]
            return loss, np.concatenate([[g0], g])

        res = minimize(f, np.zeros(k + 1), jac=True, method="L-BFGS-B", options={"maxiter": 2000})
        self.intercept_ = float(res.x[0])
        self.coef_ = res.x[1:]
        return self

    def decision_function(self, X):
        return np.asarray(X, float) @ self.coef_ + self.intercept_

    def predict_proba(self, X):
        return sigmoid(self.decision_function(X))


def auc(y, s) -> float:
    y = np.asarray(y).astype(bool)
    n1, n0 = y.sum(), (~y).sum()
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = rankdata(s)
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def brier(y, p) -> float:
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


class Isotonic:
    """Pool-adjacent-violators isotonic regression (increasing)."""

    def fit(self, x, y):
        o = np.argsort(x)
        xs, ys = np.asarray(x)[o], np.asarray(y, float)[o]
        vals, wts, xr = [], [], []
        for xi, yi in zip(xs, ys):
            vals.append(yi)
            wts.append(1.0)
            xr.append(xi)
            while len(vals) > 1 and vals[-2] > vals[-1]:
                w = wts[-2] + wts[-1]
                v = (vals[-2] * wts[-2] + vals[-1] * wts[-1]) / w
                vals[-2:] = [v]
                wts[-2:] = [w]
                xr[-2:] = [xr[-1]]
        self.x_, self.y_ = np.asarray(xr), np.asarray(vals)
        return self

    def predict(self, x):
        idx = np.clip(np.searchsorted(self.x_, x, side="left"), 0, len(self.y_) - 1)
        return self.y_[idx]


class GBM:
    """Histogram gradient boosting (logistic loss, depth-limited trees).

    Used only as an *accuracy ceiling* challenger for the scorecard.
    """

    def __init__(self, n_iter=200, lr=0.08, depth=3, bins=64, min_leaf=60, l2=1.0):
        self.n_iter, self.lr, self.depth, self.bins, self.min_leaf, self.l2 = n_iter, lr, depth, bins, min_leaf, l2

    def _binize(self, X):
        return np.column_stack([np.searchsorted(self.edges_[j], X[:, j], side="right") for j in range(X.shape[1])]).astype(np.int32)

    def fit(self, X, y):
        X = np.asarray(X, float)
        y = np.asarray(y, float)
        self.edges_ = [np.unique(np.quantile(X[:, j], np.linspace(0, 1, self.bins + 1)[1:-1])) for j in range(X.shape[1])]
        B = self._binize(X)
        p0 = np.clip(y.mean(), 1e-6, 1 - 1e-6)
        self.base_ = float(np.log(p0 / (1 - p0)))
        F = np.full(len(y), self.base_)
        self.trees_ = []
        for _ in range(self.n_iter):
            p = sigmoid(F)
            g, h = p - y, p * (1 - p)
            tree = self._grow(B, g, h, np.arange(len(y)), 0)
            self.trees_.append(tree)
            F += self.lr * self._predict_tree(tree, B)
        return self

    def _grow(self, B, g, h, idx, d):
        G, H = g[idx].sum(), h[idx].sum()
        leaf = {"v": float(-G / (H + self.l2))}
        if d >= self.depth or len(idx) < 2 * self.min_leaf:
            return leaf
        best = (0.0, None, None)
        parent = G * G / (H + self.l2)
        for j in range(B.shape[1]):
            nb = len(self.edges_[j]) + 1
            gs = np.bincount(B[idx, j], weights=g[idx], minlength=nb)
            hs = np.bincount(B[idx, j], weights=h[idx], minlength=nb)
            cs = np.bincount(B[idx, j], minlength=nb)
            gl, hl, cl = np.cumsum(gs)[:-1], np.cumsum(hs)[:-1], np.cumsum(cs)[:-1]
            ok = (cl >= self.min_leaf) & ((len(idx) - cl) >= self.min_leaf)
            if not ok.any():
                continue
            gain = gl ** 2 / (hl + self.l2) + (G - gl) ** 2 / (H - hl + self.l2) - parent
            gain[~ok] = -np.inf
            t = int(np.argmax(gain))
            if gain[t] > best[0]:
                best = (float(gain[t]), j, t)
        if best[1] is None:
            return leaf
        _, j, t = best
        left = idx[B[idx, j] <= t]
        right = idx[B[idx, j] > t]
        return {"j": j, "t": t, "l": self._grow(B, g, h, left, d + 1), "r": self._grow(B, g, h, right, d + 1)}

    def _predict_tree(self, tree, B):
        out = np.empty(B.shape[0])
        stack = [(tree, np.arange(B.shape[0]))]
        while stack:
            node, ix = stack.pop()
            if "v" in node:
                out[ix] = node["v"]
                continue
            m = B[ix, node["j"]] <= node["t"]
            stack.append((node["l"], ix[m]))
            stack.append((node["r"], ix[~m]))
        return out

    def predict_proba(self, X):
        B = self._binize(np.asarray(X, float))
        F = np.full(B.shape[0], self.base_)
        for t in self.trees_:
            F += self.lr * self._predict_tree(t, B)
        return sigmoid(F)


def average_precision(y, s) -> float:
    """Area under the precision-recall curve (step-wise average precision)."""
    y = np.asarray(y).astype(bool)
    if y.sum() == 0:
        return float("nan")
    order = np.argsort(-np.asarray(s), kind="mergesort")
    yy = y[order]
    tp = np.cumsum(yy)
    precision = tp / np.arange(1, len(yy) + 1)
    return float((precision * yy).sum() / yy.sum())


def log_loss(y, p, eps: float = 1e-12) -> float:
    p = np.clip(np.asarray(p, float), eps, 1 - eps)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
