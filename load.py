#!/usr/bin/python3

import numpy as np
from sys import argv
import struct
import matplotlib.pyplot as plt
import scipy as sp
import scipy.linalg

""" Timers from SO """
def tic():
    import time
    global startTime_for_tictoc
    startTime_for_tictoc = time.time()

def toc(label):
    import time
    if 'startTime_for_tictoc' in globals():
        print("    > " + str(time.time() - startTime_for_tictoc) + "s in " + label)
    else:
        print("Toc: start time not set")

""" Build Lagrange interpolation matrix """
def lagrange_matrix(A,B):
  M = np.zeros((B.size,A.size), order='F')
  for i in range(A.size):
    for j in range(B.size):
      M[j,i] =  1.
      for k in range(A.size):
        if k == i:
          continue
        M[j,i] = M[j,i] * (B[j] - A[k]) / (A[i] - A[k])
  return M

""" Unpack list of elements into single grid """
def elm_to_grid(pos_elm, f_elm):
  from scipy.special import cbrt
  dx = pos_elm[1,0,0] - pos_elm[0,0,0]
  print(dx)
  order = int(cbrt(pos_elm.shape[0]))
  print("Grid order " + str(order))

  origin = np.array([np.min(pos_elm[:,:,0]),
                     np.min(pos_elm[:,:,1]), 
                     np.min(pos_elm[:,:,2])])
  corner = np.array([np.max(pos_elm[:,:,0]), 
                     np.max(pos_elm[:,:,1]), 
                     np.max(pos_elm[:,:,2])])
  size = np.array((corner - origin)/dx + .5, dtype=int)+1
  print(size)
  ''' position grid '''
  pos_grid = np.zeros((size[0], size[1], size[2], 3), order='F') 
  for i in range(size[0]):
    pos_grid[i,:,:,0] = dx*i + origin[0] 
  for i in range(size[1]):
    pos_grid[:,i,:,1] = dx*i + origin[1] 
  for i in range(size[2]):
    pos_grid[:,:,i,2] = dx*i + origin[2] 

  ''' field grid '''
  f_grid = np.zeros((size[0], size[1], size[2]), order='F') 
  for i in range(pos_elm.shape[1]):
    root = np.array((pos_elm[0,i,:] - origin)/dx + .5, dtype=int)
    f_grid[root[0]:root[0]+order, 
           root[1]:root[1]+order,
           root[2]:root[2]+order] = np.reshape(f_elm[:,i], (order,order,order), order='F')

  return pos_grid, f_grid

""" Load the data """
tic()
with open(argv[1],'rb') as f:
  #''' The header is 132 bytes long '''
  header = str(f.read(132))
  htoks = header.split()
  nelm = int(htoks[5])
  norder = int(htoks[2])
  #''' Assume isotropic elements '''
  ntot = nelm * norder * norder * norder
  print("Opened {:s} and found {:d} elements of order {:d}".format(argv[1], nelm, norder)) 
  #''' Check the test float '''
  test = struct.unpack('f', f.read(4))
  print("  * test float is {}".format(test))
  #''' 4 byptes per element for an unused map '''
  element_map = f.read(nelm*4)
  #''' 4*3 bytes per basis function for position '''
  xyz  = np.fromfile(f, dtype=np.float32, count=ntot*3)
  #''' 4*3 bytes per basis function for velocity '''
  u    = np.fromfile(f, dtype=np.float32, count=norder*norder*norder*nelm*3)
  #''' 4 bytes per basis function for pressure '''
  p    = np.fromfile(f, dtype=np.float32, count=norder*norder*norder*nelm)
  #''' 4 bytes per basis function for temperature '''
  t_in = np.fromfile(f, dtype=np.float32, count=norder*norder*norder*nelm)

#''' Reshape vector data '''
pos = np.transpose(np.reshape(xyz, (norder*norder*norder,3,nelm), order='F'), (0,2,1))
vel = np.transpose(np.reshape(u, (norder*norder*norder,3,nelm), order='F'), (0,2,1))
#''' Reshape scaler data '''
t = np.reshape(t_in, (norder*norder*norder,nelm), order='F')
#''' Compute the total speed '''
speed = np.sqrt(np.square(vel[:,:,0]) + np.square(vel[:,:,1]) + np.square(vel[:,:,2]))
toc('read')

#''' Print some stuff '''
print("Extremal temperatures {:f}, {:f}".format(np.max(t), np.min(t)))
print("Extremal u_z          {:f}, {:f}".format(np.max(vel[:,:,2]), np.min(vel[:,:,2])))
print("Max speed: {:f}".format(np.max(speed)))

#''' Learn about the mesh '''
origin = np.array([np.min(pos[:,:,0].flatten()),
                   np.min(pos[:,:,1].flatten()), 
                   np.min(pos[:,:,2].flatten())])
corner = np.array([np.max(pos[:,:,0].flatten()), 
                   np.max(pos[:,:,1].flatten()), 
                   np.max(pos[:,:,2].flatten())])
extent = corner-origin
size = np.array((corner - origin)/(pos[0,1,0] - pos[0,0,0]), dtype=int)
print("Grid is ({:f}, {:f}, {:f}) [{:d}x{:d}x{:d}] with order {:d}".format(
      extent[0], extent[1], extent[2], size[0], size[1], size[2], norder))

# setup the transformation
ninterp = int(norder*2)
gll  = pos[0:norder,0,0]
dx_max = np.max(gll[1:] - gll[0:-1])
cart = np.linspace(0.,extent[0],num=ninterp,endpoint=False)/size[0]
trans = lagrange_matrix(gll,cart)
print("Cell Pe: {:f}, Cell Re: {:f}".format(np.max(speed)*dx_max/2.e-9, np.max(speed)*dx_max/1.e-7))
print("Interpolating\n" + str(gll) + "\nto\n" + str(cart))

# Apply the transformation
t_tmp = np.zeros((norder**2*ninterp,nelm), order='F')
t_tmp2 = np.zeros((norder*ninterp**2,nelm), order = 'F')
t_trans = np.zeros((ninterp**3,nelm), order = 'F')

# Transform to uniform grid
# z-first
tic()
t_p = np.reshape(np.transpose(np.reshape(t, (norder**2, norder, nelm), order='F'), (1,0,2)), (norder, norder**2*nelm), order='F')
t_tmp = np.reshape(np.transpose(np.reshape(trans.dot(t_p), (ninterp, norder**2, nelm), order='F'), (1,0,2)), (norder**2*ninterp, nelm), order='F')
toc('trans_z')

# then x
tic()
t_tmp2 = np.reshape(trans.dot(np.reshape(t_tmp, (norder, ninterp*norder*nelm), order='F')), (ninterp**2*norder,nelm), order='F')
toc('trans_x')

# then y
tic()
t_p =     np.reshape(np.transpose(np.reshape(t_tmp2,         (ninterp, norder, ninterp, nelm),  order='F'), (1,0,2,3)), (norder, ninterp**2*nelm), order='F')
t_trans = np.reshape(np.transpose(np.reshape(trans.dot(t_p), (ninterp, ninterp, ninterp, nelm), order='F'), (1,0,2,3)), (ninterp**3, nelm),        order='F')
toc('trans_y')

# Transform positions to uniform grid
tic()
pos_tmp = np.zeros((ninterp, ninterp, ninterp, 3), order='F')
pos_trans = np.zeros((ninterp**3, nelm, 3), order='F')
for i in range(nelm):
  for j in range(ninterp):
    pos_tmp[:,j,:,1] = pos[0,i,1] + cart[j]
    pos_tmp[j,:,:,0] = pos[0,i,0] + cart[j] 
    pos_tmp[:,:,j,2] = pos[0,i,2] + cart[j] 
  for j in range(3):
    pos_trans[:,i,j] = pos_tmp[:,:,:,j].flatten(order='F')
toc('trans_pos')

# Renorm
#T_low = np.min(t); T_high = np.max(t)
T_low = -0.0005; T_high = 0.0005
T = (t - T_low)/(T_high - T_low)

#Tt_low = np.min(t_trans); Tt_high = np.max(t_trans)
Tt_low = -0.0005; Tt_high = 0.0005
T_trans = (t_trans - Tt_low)/(Tt_high - Tt_low)

# extract for scatter plot
tic()
plot_x = np.zeros((size[0]*size[2])*norder**2)
plot_y = np.zeros((size[0]*size[2])*norder**2)
plot_t = np.zeros((size[0]*size[2])*norder**2)

plot_xt = np.zeros((size[0]*size[2])*ninterp**2)
plot_yt = np.zeros((size[0]*size[2])*ninterp**2)
plot_tt = np.zeros((size[0]*size[2])*ninterp**2)

ptr = 0; ptr_t = 0
center = 0.000512
plane = 1
for j in range(nelm):
  if abs(pos_trans[0,j,plane] - center) < 1.e-10:
   for i in range(norder**3):
    if abs(pos[i,j,plane] - center) < 1.e-10:
      plot_x[ptr] = pos[i,j,0]
      plot_y[ptr] = pos[i,j,2]
      plot_t[ptr] = T[i,j]
      ptr = ptr + 1

toc('reorder')
tic()
print(np.max(T_trans), np.min(T_trans))
pos_grid, t_grid = elm_to_grid(pos_trans, T_trans)
print(np.max(t_grid), np.min(t_grid))
center = int(pos_grid.shape[1]/2)
plot_xt = pos_grid[:,center,:,0].ravel()
plot_yt = pos_grid[:,center,:,2].ravel()
plot_tt = t_grid[:,center,:].ravel()
print(np.max(plot_tt), np.min(plot_tt))
print(center, t_grid.shape[1])
toc('to_grid')

tic()
cont = np.zeros((t_grid.shape[0]))
from scipy import interpolate
t_transposed = np.copy(np.transpose(t_grid, (2,0,1)), order='F')
for i in range(t_grid.shape[0]):
  f = interpolate.interp1d(pos_grid[i,center,:,2], t_transposed[:,i, center], kind='cubic') 
  z_low = np.min(pos_grid[i,center,:,2]); z_high = np.max(pos_grid[i,center,:,2])
  z_guess = (z_high + z_low)/2.
  for j in range(16):
    fz = f(z_guess)
    if fz > 0.5:
      z_low = z_guess
    else:
      z_high = z_guess
    z_guess = (z_high + z_low)/2.
  cont[i] = z_guess
toc('contour')

# Scatter plot of temperature (slice through pseudocolor in visit)
tic()
fig = plt.figure(figsize=(24,12))
ax1 = plt.subplot(1,2,1)
plt.title('GLL Scatter plot')
ax1.scatter(plot_x, plot_y, c=plot_t, s=15, linewidths = 0., alpha = 0.5)
plt.xlabel('X')
plt.ylabel('Z')
plt.axis([np.min(plot_xt), np.max(plot_xt), np.min(plot_yt), np.max(plot_yt)])
ax2 = plt.subplot(1,2,2)
plt.title('Grid Scatter plot')
ax2.scatter(plot_xt, plot_yt, c=plot_tt, s=2, linewidths = 0.)
plt.axis([np.min(plot_xt), np.max(plot_xt), np.min(plot_yt), np.max(plot_yt)])
ax2.plot(pos_grid[:,center,0,0], cont, 'k-')
plt.xlabel('X')
plt.ylabel('Z')
plt.savefig(argv[1]+'_slice.png')

# Fourier analysis in 1 dim
plt.figure()
bx1 = plt.subplot(1,2,1)
print(len(np.arange(int(t_grid.shape[0]/2+1))), len(np.fft.rfft(t_grid[:,center,int(t_grid.shape[2]/2)])))
bx1.bar(  np.arange(int(t_grid.shape[0]/2+1)),  abs(np.fft.rfft(t_grid[:,center,int(t_grid.shape[2]/2)])))
plt.title('temperature')
plt.xlabel('Mode')
plt.ylabel('Amplitude')
plt.xlim([0,10])
bx2 = plt.subplot(1,2,2)
bx2.bar(np.arange(int(t_grid.shape[0]/2+1)),abs(np.fft.rfft(cont)))
plt.title('contour')
plt.xlabel('Mode')
plt.ylabel('Amplitude')
plt.xlim([0,10])

plt.savefig(argv[1]+'_spectrum.png')

plt.figure()
ax1 = plt.subplot(1,1,1)
ax1.hist(t_grid.flatten(), bins=1000, normed=True, range=(-0.1,1.1), cumulative=True)
plt.savefig(argv[1]+'_cdf.png')
plt.show()

toc('plot')

