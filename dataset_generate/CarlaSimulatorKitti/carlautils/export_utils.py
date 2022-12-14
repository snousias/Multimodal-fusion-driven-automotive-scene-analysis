"""
This file contains all the methods responsible for saving the generated data in the correct output format.

"""

import numpy as np
from PIL import Image
import os
import logging
import math
from math import cos, sin
import aiofiles
import io


def degrees_to_radians(degrees):
    return degrees * math.pi / 180

def save_groundplanes(planes_fname, player_measurements, lidar_height):

    """ Saves the groundplane vector of the current frame.
        The format of the ground plane file is first three lines describing the file (number of parameters).
        The next line is the three parameters of the normal vector, and the last is the height of the normal vector,
        which is the same as the distance to the camera in meters.
    """
    rotation = player_measurements.get_transform().rotation
    pitch, roll = rotation.pitch, rotation.roll
    # Since measurements are in degrees, convert to radians
    pitch = degrees_to_radians(pitch)
    roll = degrees_to_radians(roll)
    # Rotate normal vector (y) wrt. pitch and yaw
    normal_vector = [cos(pitch)*sin(roll),
                     -cos(pitch)*cos(roll),
                     sin(pitch)
                     ]
    normal_vector = map(str, normal_vector)
    with open(planes_fname, 'w') as f:
        f.write("# Plane\n")
        f.write("Width 4\n")
        f.write("Height 1\n")
        f.write("{} {}\n".format(" ".join(normal_vector), lidar_height))
    logging.info("Wrote plane data to %s", planes_fname)



async def save_img_async(filename, image):
    async with aiofiles.open(filename, "wb") as file:
        await file.write(image)


def save_ref_files(OUTPUT_FOLDER, id):
    """Appends the id of the given record to the files"""
    for name in ["train.txt", "val.txt", "trainval.txt"]:
        path = os.path.join(OUTPUT_FOLDER, name)
        with open(path, 'a') as f:
            f.write("{0:06}".format(id) + '\n')
        # logging.info("Wrote reference files to %s", path)


def save_image_data(filename, image):
    # logging.info("Wrote image data to %s", filename)
    image.save_to_disk(filename)


def save_bbox_image_data(filename, image):
    im = Image.fromarray(image)
    buffer = io.BytesIO()
    im.save(buffer, format="png")
    save_img_async(filename, buffer.getbuffer())
    # im.save(filename)


def save_lidar_data(filename, point_cloud, format="bin"):
    """Saves lidar data to given filename, according to the lidar data format.
    bin is used for KITTI-data format, while .ply is the regular point cloud format
    In Unreal, the coordinate system of the engine is defined as, which is the same as the lidar points
    z
    ^   ^ x
    |  /
    | /
    |/____> y
          z
          ^   ^ x
          |  /
          | /
    y<____|/
    Which is a right handed coordinate sylstem
    Therefore, we need to flip the y axis of the lidar in order to get the correct lidar format for kitti.
    This corresponds to the following changes from Carla to Kitti
        Carla: X   Y   Z
        KITTI: X  -Y   Z
    NOTE: We do not flip the coordinate system when saving to .ply.
    """
    # logging.info("Wrote lidar data to %s", filename)

    if format == "bin":
        point_cloud = np.copy(np.frombuffer(point_cloud.raw_data, dtype=np.dtype("f4")))
        point_cloud = np.reshape(point_cloud, (int(point_cloud.shape[0] / 4), 4))
        point_cloud = point_cloud[:, :-1]

        lidar_array = [[point[0], -point[1], point[2], 1.0] for point in point_cloud]
        lidar_array = np.array(lidar_array).astype(np.float32)
        # logging.debug("Lidar min/max of x: {} {}".format(
        #              lidar_array[:, 0].min(), lidar_array[:, 0].max()))
        # logging.debug("Lidar min/max of y: {} {}".format(
        #             lidar_array[:, 1].min(), lidar_array[:, 0].max()))
        # logging.debug("Lidar min/max of z: {} {}".format(
        #              lidar_array[:, 2].min(), lidar_array[:, 0].max()))
        lidar_array.tofile(filename)


def save_label_data(filename, datapoints):

    with open(filename, 'w') as f:
        out_str = "\n".join([str(point) for point in datapoints if point])
        f.write(out_str)

    # logging.info("Wrote kitti data to %s", filename)


def save_calibration_matrices(transform, filename, intrinsic_mat):
    """Saves the calibration matrices to a file.
    AVOD (and KITTI) refers to P as P=K*[R;t], so we will just store P.
    The resulting file will contain:
    3x4    p0-p3      Camera P matrix. Contains extrinsic
                      and intrinsic parameters. (P=K*[R;t])
    3x3    r0_rect    Rectification matrix, required to transform points
                      from velodyne to camera coordinate frame.
    3x4    tr_velodyne_to_cam    Used to transform from velodyne to cam
                                 coordinate frame according to:
                                 Point_Camera = P_cam * R0_rect *
                                                Tr_velo_to_cam *
                                                Point_Velodyne.
    3x4    tr_imu_to_velo        Used to transform from imu to velodyne coordinate frame. This is not needed since we do not export
                                 imu data.
    """
    # KITTI format demands that we flatten in row-major order
    ravel_mode = "C"
    P0 = intrinsic_mat
    P0 = np.column_stack((P0, np.array([0, 0, 0])))
    P0 = np.ravel(P0, order=ravel_mode)

    camera_transform = transform[0]
    lidar_transform = transform[1]
    # pitch yaw rool
    b = math.radians(lidar_transform.rotation.pitch - camera_transform.rotation.pitch)
    x = math.radians(lidar_transform.rotation.yaw - camera_transform.rotation.yaw)
    a = math.radians(lidar_transform.rotation.roll - lidar_transform.rotation.roll)
    R0 = np.identity(3)

    TR = np.array(
        [
            [math.cos(b) * math.cos(x), math.cos(b) * math.sin(x), -math.sin(b)],
            [
                -math.cos(a) * math.sin(x) + math.sin(a) * math.sin(b) * math.cos(x),
                math.cos(a) * math.cos(x) + math.sin(a) * math.sin(b) * math.sin(x),
                math.sin(a) * math.cos(b),
            ],
            [
                math.sin(a) * math.sin(x) + math.cos(a) * math.sin(b) * math.cos(x),
                -math.sin(a) * math.cos(x) + math.cos(a) * math.sin(b) * math.sin(x),
                math.cos(a) * math.cos(b),
            ],
        ]
    )
    TR_velodyne = np.dot(TR, np.array([[1, 0, 0], [0, -1, 0], [0, 0, 1]]))

    TR_velodyne = np.dot(np.array([[0, 1, 0], [0, 0, -1], [1, 0, 0]]), TR_velodyne)

    """
    TR_velodyne = np.array([[0, -1, 0],
                            [0, 0, -1],
                            [1, 0, 0]])
    """
    # Add translation vector from velo to camera. This is 0 because the position of camera and lidar is equal in our configuration.
    TR_velodyne = np.column_stack((TR_velodyne, np.array([0, 0, 0])))
    TR_imu_to_velo = np.identity(3)
    TR_imu_to_velo = np.column_stack((TR_imu_to_velo, np.array([0, 0, 0])))

    def write_flat(f, name, arr):
        f.write(
            "{}: {}\n".format(
                name, " ".join(map(str, arr.flatten(ravel_mode).squeeze()))
            )
        )

    # All matrices are written on a line with spacing
    with open(filename, 'w') as f:
        for i in range(
            4
        ):  # Avod expects all 4 P-matrices even though we only use the first
            write_flat(f, "P" + str(i), P0)
        write_flat(f, "R0_rect", R0)
        write_flat(f, "Tr_velo_to_cam", TR_velodyne)
        write_flat(f, "TR_imu_to_velo", TR_imu_to_velo)
    # logging.info("Wrote all calibration matrices to %s", filename)


def save_rgb_image(filename, image):
    im = Image.fromarray(image)
    buffer = io.BytesIO()
    im.save(buffer, format="png")
    save_img_async(filename, buffer.getbuffer())
    # im.save(filename)
    


def save_radar_data(filename, pointclouds):
    """Appends the id of the given record to the files"""
    path = os.path.join(filename)
    f = open(path, 'a')
    points = np.frombuffer(pointclouds.raw_data, dtype=np.dtype('f4'))
    points = np.reshape(points, (len(pointclouds), 4))
    if points.size != 0:
        stuff = str(str(points).replace('[', '')).replace(']', '')
        f.write(f"{stuff}")
    
    f.close()
    # logging.info("Wrote reference files to %s", path)
    

def save_imu_data(filename, sensor_data):
    path = os.path.join(filename)
    f = open(path, 'a')
    limits = (-99.9, 99.9)

    accelerometer = (
        max(limits[0], min(limits[1], sensor_data.accelerometer.x)),
        max(limits[0], min(limits[1], sensor_data.accelerometer.y)),
        max(limits[0], min(limits[1], sensor_data.accelerometer.z)))

    s = "{} {} {}\n".format(accelerometer[0],accelerometer[1],accelerometer[2])
    f.write(s)

    gyroscope = (
        max(limits[0], min(limits[1], math.degrees(sensor_data.gyroscope.x))),
        max(limits[0], min(limits[1], math.degrees(sensor_data.gyroscope.y))),
        max(limits[0], min(limits[1], math.degrees(sensor_data.gyroscope.z))))
    
    s = "{} {} {}\n".format(gyroscope[0],gyroscope[1],gyroscope[2])
    f.write(s)
    
    s = f"{math.degrees(sensor_data.compass)}\n"
    f.write(s)
    
    f.close()
    
def save_gnss_data(filename, sensor_data):
    path = os.path.join(filename)
    f = open(path, 'a')
   
    s = "{} {} {}\n".format(sensor_data.latitude, sensor_data.longitude, sensor_data.altitude)
    f.write(s)
    
    f.close()

def save_velo_data(filename, sensor_data):
    
    path = os.path.join(filename)
    print("sensor data ",sensor_data)
    f = open(path, 'a')
   
    s = "{}\n".format(sensor_data)
    f.write(s)
    
    f.close()