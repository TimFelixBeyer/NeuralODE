import numpy as np
import matplotlib.pyplot as plt
x_train = np.load('experiments/datasets/mass_spring_damper_x_train.npy')
x_train = x_train.reshape(-1, 2)
c = np.arange(len(x_train))
np.random.shuffle(c)
x_train = x_train[c[::int(100/1)]]
plt.scatter(x_train[:, 0], x_train[:, 1], alpha=0.01)
plt.show()
plt.savefig('mass_spring_damper_train.pdf', bbox_inches='tight', pad_inches=0.)
plt.close()
x_val = np.load('experiments/datasets/mass_spring_damper_x_val.npy').reshape(-1, 2)
plt.scatter(x_val[:, 0], x_val[:, 1])
plt.savefig('mass_spring_damper_val.pdf', bbox_inches='tight', pad_inches=0.)
plt.close()
plt.figure(frameon=False)
plt.scatter(x_train[:, 0], x_train[:, 1], s=4, alpha=0.8, label='Training')
plt.scatter(x_val[:, 0], x_val[:, 1], s=4, label='Testing')
plt.xlabel('x')
plt.ylabel('x_dt')
plt.legend(loc="upper left")
plt.gca().set_aspect('equal')
# plt.gca().set_axis_off()
for spine in plt.gca().spines.values():
    spine.set_visible(False)
plt.savefig("mass_spring_damper_trainval.pdf", bbox_inches='tight', pad_inches=0.)
plt.close()
