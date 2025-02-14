from typing import Callable

import numpy as np

from idtrackerai import Blob, Fragment, Session
from idtrackerai.utils import track


def produce_trajectories(
    blobs_in_video: list[list[Blob]],
    number_of_animals: int,
    progress_bar=None,
    abort: Callable = lambda: False,
    fragments: list[Fragment] | None = None,
):
    """Produce trajectories array from ListOfBlobs

    Parameters
    ----------
    blobs_in_video : <ListOfBlobs object>
        See :class:`list_of_blobs.ListOfBlobs`
    number_of_frames : int
        Total number of frames in video
    number_of_animals : int
        Number of animals to be tracked

    Returns
    -------
    dict
        Dictionary with np.array as values (trajectories organized by identity)

    """
    number_of_frames = len(blobs_in_video)
    centroid_trajectories = np.full((number_of_frames, number_of_animals, 2), np.nan)
    id_probabilities = np.full((number_of_frames, number_of_animals, 1), np.nan)
    areas = np.full((number_of_frames, number_of_animals), np.nan)

    for frame_number, blobs_in_frame in enumerate(
        track(blobs_in_video, "Producing trajectories")
    ):
        if abort():
            return None, None, {}
        if progress_bar:
            progress_bar.emit(frame_number)
        for blob in blobs_in_frame:
            for identity, centroid in blob.final_ids_and_centroids:
                if identity not in (None, 0):
                    centroid_trajectories[blob.frame_number, identity - 1] = centroid
            blob_final_identities = list(blob.final_identities)
            if blob.is_an_individual and len(blob_final_identities) == 1:
                identity = blob_final_identities[0]
                if identity in (None, 0):
                    continue

                areas[blob.frame_number, identity - 1] = blob.area

                if fragments is None:
                    continue
                P2_vector = fragments[blob.fragment_identifier].P2_vector

                if P2_vector is None:
                    continue
                id_probabilities[blob.frame_number, identity - 1] = P2_vector.max()

    return (
        centroid_trajectories,
        id_probabilities,
        {
            "mean": np.nanmean(areas, axis=0),
            "median": np.nanmedian(areas, axis=0),
            "std": np.nanstd(areas, axis=0),
        },
    )


def produce_output_dict(
    blobs_in_video: list[list[Blob]],
    session: Session,
    fragments: list[Fragment] | None = None,
    progress_bar=None,
    abort: Callable = lambda: False,
):
    """Outputs the dictionary with keys: trajectories, git_commit, video_path,
    frames_per_second

    Parameters
    ----------
    blobs_in_video : list
        List of all blob objects (see :class:`~blob.Blobs`) generated by
        considering all the blobs segmented from the video
    session : <Session object>
        See :class:`~video.Video`

    Returns
    -------
    dict
        Output dictionary containing trajectories as values

    """

    centroid_trajectories, id_probabilities, area_stats = produce_trajectories(
        blobs_in_video, session.n_animals, progress_bar, abort, fragments
    )

    if centroid_trajectories is None or abort():
        return None

    output_dict = {
        "trajectories": centroid_trajectories / session.resolution_reduction,
        "version": session.version,
        "video_paths": list(map(str, session.video_paths)),
        "frames_per_second": session.frames_per_second,
        "body_length": session.median_body_length_full_resolution,
        "stats": {"estimated_accuracy": session.estimated_accuracy},
        "areas": area_stats,
        "setup_points": session.setup_points,
        "identities_labels": session.identities_labels
        or [str(i + 1) for i in range(session.n_animals)],
        "identities_groups": {
            key: list(value) for key, value in session.identities_groups.items()
        },
        "length_unit": session.length_unit,
    }

    if id_probabilities is not None and np.isfinite(id_probabilities).any():
        output_dict["id_probabilities"] = id_probabilities
        # After the interpolation some identities that were 0 are assigned
        output_dict["stats"]["estimated_accuracy_after_interpolation"] = (
            1 if session.single_animal else np.nanmean(output_dict["id_probabilities"])
        )
        # Centroids with identity
        identified = ~np.isnan(output_dict["trajectories"][..., 0])
        output_dict["stats"]["percentage_identified"] = np.mean(identified)
        # Estimated accuracy of identified blobs

        output_dict["stats"]["estimated_accuracy_identified"] = (
            1
            if session.single_animal
            else np.nanmean(output_dict["id_probabilities"][identified])
        )

    return output_dict
