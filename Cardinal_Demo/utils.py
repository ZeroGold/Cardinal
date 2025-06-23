# utils.py
import math

def euclidean_distance(point1, point2):
    """
    Calculates the Euclidean distance between two 2D points (tuples or lists of x, y).
    Used for matching detected objects to tracked objects based on their centroids.
    """
    return math.sqrt((point2[0] - point1[0])**2 + (point2[1] - point1[1])**2)

def intersect_line_segments(p1, p2, p3, p4):
    """
    Checks if two line segments (p1, p2) and (p3, p4) intersect.
    
    p1: (x, y) tuple representing the previous centroid of a tracked object.
    p2: (x, y) tuple representing the current centroid of a tracked object.
    p3: (x, y) tuple representing the start point of the counting line.
    p4: (x, y) tuple representing the end point of the counting line.

    This function is critical for accurate line crossing detection. The provided
    implementation below is a simplified version, primarily for horizontal lines,
    and demonstrates the concept. For robust, general line-segment intersection
    (especially for arbitrary line orientations), you would typically use a more
    sophisticated algorithm involving cross products or Cramer's rule, like:
    - https://www.geeksforgeeks.org/check-if-two-given-line-segments-intersect/
    - A custom implementation or a geometry library if available.

    For the typical shelf inventory scenario with a horizontal line, checking
    if the object's Y coordinate crosses the line's Y, and if its X projection
    is within the line's X bounds, is often sufficient.
    """
    
    # Assuming a horizontal counting line for simplicity (p3[1] == p4[1])
    line_y = p3[1] 
    
    # 1. Check if the object's path straddles the horizontal line's Y-coordinate.
    # This means one point is above the line and the other is below (or on) the line.
    straddles_y = (p1[1] < line_y and p2[1] >= line_y) or \
                  (p1[1] > line_y and p2[1] <= line_y)

    if not straddles_y:
        return False

    # 2. Check if the X-projection of the object's path at the line's Y-level
    # falls within the X-bounds of the counting line segment.
    # This ensures the object actually crossed the line, not just its Y-level.

    min_line_x = min(p3[0], p4[0])
    max_line_x = max(p3[0], p4[0])
    
    # Calculate the X coordinate of the point where the object's path intersects the line's Y-level.
    # This uses linear interpolation.
    if (p2[1] - p1[1]) == 0: # Avoid division by zero for purely horizontal movement
        # If moving purely horizontally, check if its X is within line's X bounds
        interpolated_x = p1[0] 
    else:
        # Calculate intersection X using ratio of Y-distances
         interpolated_x = p1[0] + (p2[0] - p1[0]) * ((line_y - p1[1]) / (p2[1] - p1[1]))
