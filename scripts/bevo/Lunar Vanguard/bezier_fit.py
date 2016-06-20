'''least square qbezier fit using penrose pseudoinverse
    >>> V=array
    >>> E,  W,  N,  S =  V((1,0)), V((-1,0)), V((0,1)), V((0,-1))
    >>> cw = 100
    >>> ch = 300
    >>> cpb = V((0, 0))
    >>> cpe = V((cw, 0))
    >>> xys=[cpb,cpb+ch*N+E*cw/8,cpe+ch*N+E*cw/8, cpe]            
    >>> 
    >>> ts = V(range(11))/10
    >>> M = bezierM (ts)
    >>> points = M*xys #produces the points on the bezier curve at t in ts
    >>> 
    >>> control_points=lsqfit(points, M)
    >>> linalg.norm(control_points-xys)<10e-5
    True
    >>> control_points.tolist()[1]
    [12.500000000000037, 300.00000000000017]

'''
from numpy import array, linalg, matrix
from scipy.misc import comb as nOk
Mtk = lambda n, t, k: t**(k)*(1-t)**(n-k)*nOk(n,k)
bezierM = lambda ts: matrix([[Mtk(3,t,k) for k in range(4)] for t in ts])
def lsqfit(points,M):
    M_ = linalg.pinv(M)
    return M_ * points